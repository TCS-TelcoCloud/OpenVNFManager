#copyright 2014 Tata Consultancy Services Ltd.
from vnfsvcclient.common import exceptions
from vnfsvcclient.vnfsvc import v1_0 as vnfsvcV20
from vnfsvcclient.openstack.common.gettextutils import _

_ACTIVATES = 'activate'

class ActivateService(vnfsvcV20.CreateCommand):
    """ENABLE a VNF service."""
    resource = _ACTIVATES
    def add_known_arguments(self, parser):
        parser.add_argument(
            '--name',
            required=True,
            help='name of the service')
        parser.add_argument(
            '--template_id',
            required=True,
            help='Template id')
        parser.add_argument(
            '--enable',
            required=True,
            help='provide information to enable')

    def args2body(self, parsed_args):
        body = {
            self.resource: {
                'name': parsed_args.name,
                'template_id' : parsed_args.template_id,
                'enable': parsed_args.enable,
            }
        }
        parsed_args.enable = parsed_args.enable.lower()
        #check the flag
        if parsed_args.enable != 'true' and parsed_args.enable != 'false':
           raise exceptions.UserInputHandler(error_message='True/False')

        vnfsvcV20.update_dict(parsed_args, body[self.resource], ['tenant_id'])
        return body
