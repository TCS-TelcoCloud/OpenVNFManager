# Copyright 2014 Tata Consultancy Services Ltd.
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



# If ../vnfsvc/__init__.py exists, add ../ to Python search path, so that
# it will override what happens to be installed in /usr/(local/)lib/python...

import sys

import eventlet
eventlet.monkey_patch()

from oslo_config import cfg

from vnfsvc.common import config
from vnfsvc import service
from vnfsvc.openstack.common.gettextutils import _

def main():
    # the configuration will be read into the cfg.CONF global data structure
    config.init(sys.argv[1:])
    if not cfg.CONF.config_file:
        sys.exit(_("ERROR: Unable to find configuration file via the default"
                   " search paths (~/.vnfsvc/, ~/, /etc/vnfsvc/, /etc/) and"
                   " the '--config-file' option!"))
    try:
        pool = eventlet.GreenPool()

        vnfsvc_api = service.serve_wsgi(service.VNFSvcApiService)
        api_thread = pool.spawn(vnfsvc_api.wait)

        pool.waitall()
    except KeyboardInterrupt:
        pass
    except RuntimeError as e:
        sys.exit(_("ERROR: %s") % e)


if __name__ == "__main__":
    main()
