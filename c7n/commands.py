# Copyright 2016 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from datetime import timedelta, datetime
from functools import wraps
import json
import logging
import os
import sys
import time

import yaml

from c7n.config import Config
from c7n.credentials import SessionFactory
from c7n.reports import report as do_report
from c7n import mu, schema, policy


log = logging.getLogger('custodian.commands')


def policy_command(f):

    @wraps(f)
    def _load_policies(options):
        config = Config()
        config.from_cli(options)
        collection = policy.load(options, options.config)
        return f(config, collection)


def validate(options):
    if not os.path.exists(options.config):
        raise ValueError("Invalid path for config %r" % options.config)

    format = options.config.rsplit('.', 1)[-1]
    with open(options.config) as fh:
        if format in ('yml', 'yaml'):
            data = yaml.safe_load(fh.read())
        if format in ('json',):
            data = json.load(fh)

    errors = schema.validate(data)
    if not errors:
        log.info("Config valid")
        return

    log.error("Invalid configuration")
    for e in errors:
        log.error(" %s" % e)
    sys.exit(1)


@policy_command
def run(options, policy_collection):
    for policy in policy_collection.policies(options.policies):
        try:
            policy()
        except Exception:
            if options.debug:
                raise
            # Output does an exception log
            log.warning("Error while executing policy %s, continuing" % (
                policy.name))


@policy_command
def report(options, policy_collection):
    policies = policy_collection.policies(options.policies)
    assert len(policies) == 1, "Only one policy report at a time"
    policy = policies.pop()
    d = datetime.now()
    delta = timedelta(days=options.days)
    begin_date = d - delta
    do_report(
        policy, begin_date, sys.stdout,
        raw_output_fh=options.raw)


@policy_command
def logs(options, policy_collection):
    policies = policy_collection.policies(options.policies)
    assert len(policies) == 1, "Only one policy log at a time"
    policy = policies.pop()

    if not policy.is_lambda:
        log.debug('lambda only atm')
        return

    session_factory = SessionFactory(
        options.region, options.profile, options.assume_role)
    manager = mu.LambdaManager(session_factory)
    for e in manager.logs(mu.PolicyLambda(policy)):
        print "%s: %s" % (
            time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(e['timestamp'] / 1000)),
            e['message'])


@policy_command
def resources(options, policy_collection):
    import yaml
    session_factory = SessionFactory(
        options.region, options.profile, options.assume_role)
    manager = mu.LambdaManager(session_factory)
    funcs = manager.list_functions('custodian-')

    if options.all:
        print(yaml.dump(funcs, dumper=yaml.SafeDumper))


def resources_gc(options, policy_collection):
    pass