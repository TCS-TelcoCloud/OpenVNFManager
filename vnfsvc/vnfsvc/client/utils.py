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

import re

from oslo_utils import encodeutils
from vnfsvc.common import exceptions


def find_resource(resource_list, name_or_id, **find_args):
    """Helper for the _find_* methods."""
    for resource in resource_list:
        match = re.match(resource.__dict__[find_args['pattern']],name_or_id)
        if match:
            return resource
