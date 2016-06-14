# Copyright 2014 Tata Consultancy Services Ltd.

from vnfsvcclient.common import exceptions
from vnfsvcclient.vnfsvc import v1_0 as vnfsvcV20
from vnfsvcclient.openstack.common.gettextutils import _


_SERVICE = 'service'


class ListService(vnfsvcV20.ListCommand):
    """List service that belong to a given tenant."""

    resource = _SERVICE


class ShowService(vnfsvcV20.ShowCommand):
    """Show information of a given VNF."""

    resource = _SERVICE


class CreateService(vnfsvcV20.CreateCommand):
    """Create a VNF service."""

    resource = _SERVICE

    def add_known_arguments(self, parser):
        parser.add_argument(
            '--name',
            required=True,
            help='name of the service')
        parser.add_argument(
            '--qos',
            required=True,
            help='quality of service')
        parser.add_argument(
            '--networks',
            metavar='<key>=<value>',
            action='append',
            dest='networks',
            default=[],
            help='network details')
        parser.add_argument(
            '--router',
            required=True,
            help='Router details')
        parser.add_argument(
            '--subnets',
            metavar='<key:subnet_name>=<value:subnet_id>',
            action='append',
            dest='subnets',
            default=[],
            help='subnet details')
    

    def args2body(self, parsed_args):
        body = {
            self.resource: {
                'name': parsed_args.name,
                'quality_of_service' : parsed_args.qos,
                'attributes': dict()
            }
        }


        if parsed_args.networks:
            try:
                kwargs = dict(key_value.split('=', 1)
                              for key_value in parsed_args.networks)
            except ValueError:
                msg = (_('invalid argument for --kwargs %s') %
                       parsed_args.kwargs)
                raise exceptions.vnfsvcCLIError(msg)
            if kwargs:
                body[self.resource]['attributes']['networks'] = kwargs


        if parsed_args.router:
            body[self.resource]['attributes']['router'] = parsed_args.router
      
        if parsed_args.subnets:
            try:
                kwargs = dict(key_value.split('=', 1)
                              for key_value in parsed_args.subnets)
            except ValueError:
                msg = (_('invalid argument for --kwargs %s') %
                       parsed_args.kwargs)
                raise exceptions.vnfsvcCLIError(msg)
            if kwargs:
                body[self.resource]['attributes']['subnets'] = kwargs


        vnfsvcV20.update_dict(parsed_args, body[self.resource], ['tenant_id'])
        return body


class DeleteService(vnfsvcV20.DeleteCommand):
    """Delete a given VNF service."""
    resource = _SERVICE

class UpdateService(vnfsvcV20.UpdateCommand):
    """Update a given VNF service."""

    resource = _SERVICE

    def add_known_arguments(self, parser):
        parser.add_argument(
            '--vdu-name',
            required=True,
            help='name of the service')
        parser.add_argument(
            '--updation-cmd',
            required=True,
            help='updation key-value pairs')

    def args2body(self, parsed_args):
        updation_method = eval(parsed_args.updation_cmd).keys()[0]
        updation_args = eval(parsed_args.updation_cmd).values()[0]
        body = {
            self.resource: { 'attributes':
                {
                'vdu_name': parsed_args.vdu_name,
                'method': updation_method,
                'arguments': updation_args
                }
            }
        }
        vnfsvcV20.update_dict(parsed_args, body[self.resource], ['tenant_id'])
        return body


