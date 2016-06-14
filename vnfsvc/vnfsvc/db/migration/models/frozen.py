# Copyright (c) 2014 Tata Consultancy Services Ltd.
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
The module provides all database models.

Its purpose is to create comparable metadata with current database schema.
Based on this comparison database can be healed with healing migration.

Current HEAD commit is 59da928e945ec58836d34fd561d30a8a446e2728
"""


import sqlalchemy as sa
from sqlalchemy.ext import declarative
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy import orm
from sqlalchemy import schema

from vnfsvc.db import model_base
from vnfsvc.openstack.common import uuidutils


# Dictionary of all tables that was renamed:
# {new_table_name: old_table_name}

UUID_LEN = 36
STR_LEN = 255


BASEV2 = declarative.declarative_base(cls=model_base.VNFSvcBaseV2)

class HasTenant(object):
    tenant_id = sa.Column(sa.String(255))


class HasId(object):
    id = sa.Column(sa.String(36),
                   primary_key=True,
                   default=uuidutils.generate_uuid)


class NetworkService(model_base.BASEV2):
    """Represents Network service details
    """
    id = sa.Column(sa.String(36), primary_key=True, nullable=False)
    vnfm_id = sa.Column(sa.String(4000),nullable=False)
    vnfm_host = sa.Column(sa.String(4000),nullable=True)
    vdus = sa.Column(sa.String(4000), nullable=False)
    networks = sa.Column(sa.String(4000), nullable=False)
    subnets = sa.Column(sa.String(4000), nullable=False)
    router = sa.Column(sa.String(4000), nullable=False)
    service_type = sa.Column(sa.String(36), nullable=False)
    #puppet_id = sa.Column(sa.String(36), nullable=False)
    status = sa.Column(sa.String(36), nullable=False)
    template_id = sa.Column(sa.String(36), nullable=False)
    flavour = sa.Column(sa.String(36), nullable=False)
    xml = sa.Column('xml',sa.Text(4000),nullable=False)


class Vdu(model_base.BASEV2):
    """Represents Virtual Deployment Unit details
    """
    id = sa.Column(sa.String(36), primary_key=True,nullable=False)
    instances = sa.Column(sa.String(4000),nullable=False)
    flavor = sa.Column(sa.String(36),nullable=False)
    image = sa.Column(sa.String(36),nullable=False)
    lf_event = sa.Column(sa.String(4000),nullable=False)
    userdata = sa.Column(sa.String(4000),nullable=True)


class ServiceTemplate(model_base.BASEV2):
    """Represents Service template details
    """
    id = sa.Column(sa.String(36), primary_key=True,nullable=False)
    service_type = sa.Column(sa.String(36),nullable=False)
    template_path = sa.Column(sa.String(4000),nullable=False)
    parser = sa.Column(sa.String(36),nullable=False)
    version = sa.Column(sa.String(36),nullable=False)
    status = sa.Column(sa.String(36),nullable=False)
    specs = sa.Column(sa.String(5000),nullable=False)


class VduConfiguration(model_base.BASEV2):
    """Represents Virtual Deployment Unit configuration
    """
    template_id = sa.Column(sa.String(36), sa.ForeignKey('ServiceTemplate.id'), primary_key=True,nullable=False)
    vdu_name = sa.Column(sa.String(36),primary_key=True, nullable=False)
    flavour = sa.Column(sa.String(36), primary_key=True, nullable=False)
    image_id = sa.Column(sa.String(36), nullable=False)
    vdu_flavor = sa.Column(sa.String(36), nullable=False)
    Configuration = sa.Column(sa.String(4000),nullable=False)

class User(model_base.BASEV2):
    """Represents Registered Users
    """
    id = sa.Column(sa.String(36), primary_key=True,nullable=False)
    username = sa.Column(sa.String(36),nullable=False)
    password = sa.Column(sa.String(36),nullable=False)
    template_id = sa.Column(sa.String(36),nullable=False)
    nsd_id = sa.Column(sa.String(36),nullable=True)
    endpoint = sa.Column(sa.String(4000),nullable=False)

def get_metadata():
    return BASEV2.metadata
