#!/usr/bin/env python
# Copyright 2013 Brett Slatkin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Background worker that uploads new release candidates."""

import hashlib
import os

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
import capture_worker
import pdiff_worker
import workers


gflags.DEFINE_string(
    'release_server_prefix', None,
    'URL prefix of where the release server is located, such as '
    '"http://www.example.com/here/is/my/api".')


class Error(Exception):
    """Base-class for exceptions in this module."""

class CreateReleaseError(Error):
    """Creating a new release failed for some reason."""

class UploadFileError(Error):
    """Uploading a file failed for some reason."""

class ReportRunError(Error):
    """Reporting a run failed for some reason."""

class RunsDoneError(Error):
    """Marking that all runs are done failed for some reason."""


class StreamingSha1File(file):
    """File sub-class that sha1 hashes the data as it's read."""

    def __init__(self, *args, **kwargs):
        """Replacement for open()."""
        file.__init__(self, *args, **kwargs)
        self.sha1 = hashlib.sha1()

    def read(self, *args):
        data = file.read(self, *args)
        self.sha1.update(data)
        return data

    def close(self):
        file.close(self)

    def hexdigest(self):
        return self.sha1.hexdigest()


class CreateReleaseWorkflow(workers.WorkflowItem):
    """Creates a new release candidate.

    Args:
        build_id: ID of the build.
        release_name: Name of the release candidate.

    Returns:
        Tuple (build_id, release_name, release_number).

    Raises:
        CreateReleaseError if the release could not be created.
    """

    def run(self, build_id, release_name):
        call = yield workers.FetchItem(
            FLAGS.release_server_prefix + '/create_release',
            post={
                'build_id': build_id,
                'release_name': release_name,
            })

        if call.json and call.json.get('error'):
            raise CreateReleaseError(call.json.get('error'))

        if not call.json or not call.json.get('release_number'):
            raise CreateReleaseError('Bad response: %r' % call)

        raise workers.Return(
            (build_id, release_name, call.json['release_number']))


class UploadFileWorkflow(workers.WorkflowItem):
    """Uploads a file for a build.

    Args:
        file_path: Path to the file to upload.

    Returns:
        sha1 sum of the file's contents or None if the file could not
        be found.

    Raises:
        UploadFileError if the file could not be uploaded.
    """

    def run(self, file_path):
        try:
            handle = StreamingSha1File(file_path, 'rb')
            upload = yield workers.FetchItem(
                FLAGS.release_server_prefix + '/upload',
                post={'file': handle},
                timeout_seconds=120)

            if upload.json and upload.json.get('error'):
                raise UploadFileError(upload.json.get('error'))

            sha1sum = handle.hexdigest()
            if not upload.json or upload.json.get('sha1sum') != sha1sum:
                raise UploadFileError('Bad response: %r' % upload)

            raise workers.Return(sha1sum)

        except IOError:
            raise workers.Return(None)


class ReportRunWorkflow(workers.WorkflowItem):
    """Reports a run as finished.

    Args:
        build_id: ID of the build.
        release_name: Name of the release.
        release_number: Number of the release candidate.
        run_name: Name of the run being uploaded.
        screenshot_path: Path to the screenshot to upload.
        log_path: Path to the screenshot log to upload.
        config_path: Path to the config to upload.

    Raises:
        ReportRunError if the run could not be reported.
    """

    def run(self, build_id, release_name, release_number, run_name,
            screenshot_path, log_path, config_path):
        screenshot_id, log_id, config_id = yield [
            UploadFileWorkflow(screenshot_path),
            UploadFileWorkflow(log_path),
            UploadFileWorkflow(config_path),
        ]

        call = yield workers.FetchItem(
            FLAGS.release_server_prefix + '/report_run',
            post={
                'build_id': build_id,
                'release_name': release_name,
                'release_number': release_number,
                'run_name': run_name,
                'image': screenshot_id,
                'log': log_id,
                'config': config_id,
            })

        if call.json and call.json.get('error'):
            raise ReportRunError(call.json.get('error'))

        if not call.json or not call.json.get('success'):
            raise ReportRunError('Bad response: %r' % call)


class ReportPdiffWorkflow(workers.WorkflowItem):
    """TODO"""

    def run(self, diff_path, diff_log, run_id):
        pass
        # upload the diff image
        # upload the diff log
        # report the fact that it's done


class RunsDoneWorkflow(workers.WorkflowItem):
    """TODO"""

    def run(self, build_id, release_name, release_number):
        call = yield workers.FetchItem(
            FLAGS.release_server_prefix + '/runs_done',
            post={
                'build_id': build_id,
                'release_name': release_name,
                'release_number': release_number,
            })

        if call.json and call.json.get('error'):
            raise RunsDoneError(call.json.get('error'))

        if not call.json or not call.json.get('success'):
            raise RunsDoneError('Bad response: %r' % call)

        raise workers.Return('this would be a URL')
