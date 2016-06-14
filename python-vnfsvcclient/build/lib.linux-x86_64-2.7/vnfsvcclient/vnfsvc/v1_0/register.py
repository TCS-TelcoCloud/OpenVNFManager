# Copyright 2014 Tata Consultancy Services Ltd.

from vnfsvcclient.common import exceptions
from vnfsvcclient.vnfsvc import v1_0 as vnfsvcV20
from vnfsvcclient.openstack.common.gettextutils import _


_REGISTER = 'register'

class CreateUser(vnfsvcV20.CreateCommand):
    """Create a User."""

    resource = _REGISTER

    def add_known_arguments(self, parser):
        parser.add_argument(
            '--username',
            required=True,
            help='name of the user')
        parser.add_argument(
            '--password',
            required=True,
            help='password')
        parser.add_argument(
            '--userendpoint',
            required=True,
            default=[],
            help='User endpoint')
        parser.add_argument(
            '--template-id',
            required=True,
            default=[],
            help='ID of the template')
        parser.add_argument(
            '--nsd-id',
            default=[],
            help='ID of the network service')

    def args2body(self, parsed_args):
        body = {
            self.resource: {
                "user":{
                'username': parsed_args.username,
                'password' : parsed_args.password,
                'endpoints': parsed_args.userendpoint,
                'template_id': parsed_args.template_id
                }
            }
        }
        if parsed_args.nsd_id:
            kwargs = parsed_args.nsd_id
            body[self.resource]['nsd_id'] = kwargs
        vnfsvcV20.update_dict(parsed_args, body[self.resource], ['tenant_id'])
        return body

