from vnfsvcclient.common import exceptions
from vnfsvcclient.vnfsvc import v1_0 as vnfsvcV20
from vnfsvcclient.openstack.common.gettextutils import _
from vnfsvcclient.common.yamlutil import ordered_load
import zipfile
import tempfile
import yaml
import json
import os

_TEMPLATE = 'template'


class ListTemplate(vnfsvcV20.ListCommand):
    """List templates."""

    resource = _TEMPLATE

class ShowTemplate(vnfsvcV20.ShowCommand):
    """Show information of a given template."""

    resource = _TEMPLATE

class CreateTemplate(vnfsvcV20.CreateCommand):
    """Creates Descriptor Templates."""

    resource = _TEMPLATE

    def add_known_arguments(self, parser):
        parser.add_argument(
            '--name',
            required=True,
            help='name of the template')
        parser.add_argument(
            '--file',
            help='path of the zip file')

    def args2body(self, parsed_args):
        body = {
            self.resource: {
                'name': parsed_args.name,
            }
        }
        if parsed_args.file:
            body[self.resource]['files'] = {}
            #newpath = os.environ['HOME']+"/vnfsvc_templates/"+body['template']['name']
            newpath = tempfile.mkdtemp()
            #if not os.path.exists(newpath):
            #    os.makedirs(newpath)
            with zipfile.ZipFile(parsed_args.file) as zipfi:
                zipfi.extractall(newpath+"/")
            for filename in zipfi.namelist():
                body[self.resource]['files'][filename] = json.dumps(ordered_load(open(newpath+"/"+filename,'r'), yaml.SafeLoader))
        vnfsvcV20.update_dict(parsed_args, body[self.resource], ['tenant_id'])
        return body


class DeleteTemplate(vnfsvcV20.DeleteCommand):
    """Delete Templates."""

    resource = _TEMPLATE

