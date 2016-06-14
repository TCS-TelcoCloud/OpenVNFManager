# Copyright (c) 2014 Tata Consultancy Services Limited(TCSL).
# Copyright (c) 2012 OpenStack Foundation.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import itertools
import oslo_messaging

from vnfmanager.common import rpc as v_rpc
from vnfmanager.common import topics

from vnfmanager.openstack.common import log as logging
from vnfmanager.openstack.common import timeutils


LOG = logging.getLogger(__name__)


def create_consumers(endpoints, prefix, topic_details):
    """Create agent RPC consumers.

    :param endpoints: The list of endpoints to process the incoming messages.
    :param prefix: Common prefix for the plugin/agent message queues.
    :param topic_details: A list of topics. Each topic has a name, an
                          operation, and an optional host param keying the
                          subscription to topic.host for plugin calls.

    :returns: A common Connection.
    """

    connection = v_rpc.create_connection(new=True)
    for details in topic_details:
        topic, operation, node_name = itertools.islice(
            itertools.chain(details, [None]), 3)

        topic_name = topics.get_topic_name(prefix, topic, operation)
        connection.create_consumer(topic_name, endpoints, fanout=True)
        if node_name:
            node_topic_name = '%s.%s' % (topic_name, node_name)
            connection.create_consumer(node_topic_name,
                                       endpoints,
                                       fanout=False)
    connection.consume_in_threads()
    return connection


class PluginReportStateAPI(v_rpc.RpcProxy):
    BASE_RPC_API_VERSION = '1.0'

    def __init__(self, topic):
        super(PluginReportStateAPI, self).__init__(
            topic=topic, default_version=self.BASE_RPC_API_VERSION)

    def report_state(self, context, agent_state, use_call=False):
        msg = self.make_msg('report_state',
                            agent_state={'agent_state':
                                         agent_state},
                            time=timeutils.strtime())
        if use_call:
            return self.call(context, msg)
        else:
            return self.cast(context, msg)


