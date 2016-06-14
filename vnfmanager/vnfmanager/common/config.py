# Copyright 2014,Tata Consultancy Services Ltd.
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

"""
Routines for configuring Vnfsvc
"""

import os

from oslo_config import cfg
from oslo_db import options as db_options
import oslo_messaging as messaging
from paste import deploy

from vnfmanager.common import utils
from vnfmanager.openstack.common import log as logging
from vnfmanager import version
from vnfmanager.common import rpc as n_rpc
from vnfmanager.openstack.common.gettextutils import _

LOG = logging.getLogger(__name__)

core_opts = [
    cfg.StrOpt('bind_host', default='0.0.0.0',
               help=_("The host IP to bind to")),
    cfg.StrOpt('host', default=utils.get_hostname(),
               help=_("The hostname Vnfsvc is running on")),
]
""" cfg.IntOpt('bind_port', default=9010,
               help=_("The port to bind to")),
    cfg.StrOpt('api_paste_config', default="api-paste.ini",
               help=_("The API paste config file to use")),
    cfg.StrOpt('api_extensions_path', default="",
               help=_("The path for API extensions")),
    cfg.StrOpt('policy_file', default="policy.json",
               help=_("The policy file to use")),
    cfg.StrOpt('auth_strategy', default='keystone',
               help=_("The type of authentication to use")),
    cfg.StrOpt('core_plugin',
               help=_("The core plugin Vnfsvc will use")),
    cfg.BoolOpt('allow_bulk', default=True,
                help=_("Allow the usage of the bulk API")),
    cfg.BoolOpt('allow_pagination', default=False,
                help=_("Allow the usage of the pagination")),
    cfg.BoolOpt('allow_sorting', default=False,
                help=_("Allow the usage of the sorting")),
    cfg.StrOpt('pagination_max_limit', default="-1",
               help=_("The maximum number of items returned in a single "
                      "response, value was 'infinite' or negative integer "
                      "means no limit")),
    cfg.StrOpt('nova_url',
               default='http://127.0.0.1:8774/v2',
               help=_('URL for connection to nova')),
    cfg.StrOpt('nova_admin_username',
               help=_('Username for connecting to nova in admin context')),
    cfg.StrOpt('nova_admin_password',
               help=_('Password for connection to nova in admin context'),
               secret=True),
    cfg.StrOpt('nova_admin_tenant_id',
               help=_('The uuid of the admin nova tenant')),
    cfg.StrOpt('nova_admin_auth_url',
               default='http://localhost:5000/v2.0',
               help=_('Authorization URL for connecting to nova in admin '
                      'context')),
    cfg.StrOpt('nova_ca_certificates_file',
               help=_('CA file for novaclient to verify server certificates')),
    cfg.BoolOpt('nova_api_insecure', default=False,
                help=_("If True, ignore any SSL validation issues")),
    cfg.StrOpt('nova_region_name',
               help=_('Name of nova region to use. Useful if keystone manages'
                      ' more than one region.')),
    cfg.IntOpt('send_events_interval', default=2,
               help=_('Number of seconds between sending events to nova if '
                      'there are any events to send.')),

    core_cli_opts = [
    cfg.StrOpt('state_path',
               default='/var/lib/nfvsvc',
               help=_("Where to store NFV Service state files. "
                      "This directory must be writable by the agent.")),
]
"""
# Register the configuration options
cfg.CONF.register_opts(core_opts)
#cfg.CONF.register_cli_opts(core_cli_opts)

# Ensure that the control exchange is set correctly
messaging.set_transport_defaults(control_exchange='vnfsvc')
_SQL_CONNECTION_DEFAULT = 'sqlite://'
# Update the default QueuePool parameters. These can be tweaked by the
# configuration variables - max_pool_size, max_overflow and pool_timeout
db_options.set_defaults(cfg.CONF,
                        connection=_SQL_CONNECTION_DEFAULT,
                        sqlite_db='', max_pool_size=10,
                        max_overflow=20, pool_timeout=10)


def init(args, **kwargs):
    cfg.CONF(args=args, project='vnfsvc',
             version='%%prog %s' % version.version_info.release_string(),
             **kwargs)

    # FIXME(ihrachys): if import is put in global, circular import
    # failure occurs
    from vnfmanager.common import rpc as n_rpc
    n_rpc.init(cfg.CONF)


def setup_logging(conf):
    """Sets up the logging options for a log with supplied name.

    :param conf: a cfg.ConfOpts object
    """
    product_name = "vnfsvc"
    logging.setup(product_name)
    LOG.info(_("Logging enabled!"))
