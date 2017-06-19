#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import random

from mistral.actions import base
from oslo_config import cfg
from oslo_log import log as logging

from tacker.agent.linux import utils as linux_utils
from tacker.common import rpc
from tacker.common import topics


LOG = logging.getLogger(__name__)


class PingVimAction(base.Action):

    def __init__(self, count, targetip, vim_id,
                 interval, timeout):
        self.killed = False
        self.count = count
        self.timeout = timeout
        self.interval = interval
        self.targetip = targetip
        self.vim_id = vim_id
        self.current_status = "PENDING"

    def start_rpc_listeners(self):
        """Start the RPC loop to let the server communicate with actions."""
        self.endpoints = [self]
        self.conn = rpc.create_connection()
        self.conn.create_consumer(topics.TOPIC_ACTION_KILL,
                                  self.endpoints, fanout=False,
                                  host=self.vim_id)
        return self.conn.consume_in_threads()

    def killAction(self, context, **kwargs):
        self.killed = True

    def _ping(self):
        ping_cmd = ['ping', '-c', self.count,
                    '-W', self.timeout,
                    '-i', self.interval,
                    self.targetip]

        try:
            linux_utils.execute(ping_cmd, check_exit_code=True)
            return 'REACHABLE'
        except RuntimeError:
            LOG.warning(("Cannot ping ip address: %s"), self.targetip)
            return 'UNREACHABLE'

    def _update(self, status):
        # TODO(liuqing) call tacker conductor
        LOG.info("VIM %s changed to status %s", self.vim_id, status)
        x = random.randint(1, 10)
        if 0 == (x % 2):
            return 'UNREACHABLE'
        else:
            return 'REACHABLE'
        return status

    def run(self):
        servers = []
        try:
            rpc.init_action_rpc(cfg.CONF)
            servers = self.start_rpc_listeners()
        except Exception:
            LOG.exception('failed to start rpc in vim action')
            return 'FAILED'
        try:
            while True:
                if self.killed:
                    break
                status = self._ping()
                if self.current_status != status:
                    self.current_status = self._update(status)
        except Exception:
            LOG.exception('failed to run mistral action for vim %s',
                          self.vim_id)
            return 'FAILED'
        # to stop rpc connection
        for server in servers:
            try:
                server.stop()
            except Exception:
                LOG.exception(
                    'failed to stop rpc connection for vim %s',
                    self.vim_id)
        return 'KILLED'

    def test(self):
        return 'REACHABLE'
