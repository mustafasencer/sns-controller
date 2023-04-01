# Copyright Amazon.com Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may
# not use this file except in compliance with the License. A copy of the
# License is located at
#
#	 http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

"""Integration tests for the SNS Subscription resource"""

import time

import pytest

from acktest.k8s import condition
from acktest.k8s import resource as k8s
from acktest.resources import random_suffix_name
from e2e import service_marker, CRD_GROUP, CRD_VERSION, load_resource
from e2e.bootstrap_resources import get_bootstrap_resources
from e2e.common.types import SUBSCRIPTION_RESOURCE_PLURAL
from e2e.replacement_values import REPLACEMENT_VALUES
from e2e import subscription
from e2e import tag
from e2e import topic

MODIFY_WAIT_AFTER_SECONDS = 10
CHECK_WAIT_AFTER_REF_RESOLVE_SECONDS = 10
DELETE_SUBSCRIPTION_TIMEOUT_SECONDS = 10


@pytest.fixture(scope="module")
def subscription_sqs():
    subscription_name = random_suffix_name("subscription-sqs", 24)
    display_name  = "a subscription to a queue"

    boot_resources = get_bootstrap_resources()
    q = boot_resources.Queue
    topic = boot_resources.Topic

    replacements = REPLACEMENT_VALUES.copy()
    replacements['SUBSCRIPTION_NAME'] = subscription_name
    replacements['TOPIC_ARN'] = topic.arn
    replacements['ENDPOINT'] = q.arn

    resource_data = load_resource(
        "subscription_with_refs",
        additional_replacements=replacements,
    )

    ref = k8s.CustomResourceReference(
        CRD_GROUP, CRD_VERSION, SUBSCRIPTION_RESOURCE_PLURAL,
        subscription_name, namespace="default",
    )
    k8s.create_custom_resource(ref, resource_data)
    cr = k8s.wait_resource_consumed_by_controller(ref)

    assert cr is not None
    assert k8s.get_resource_exists(ref)
    # NOTE(jaypipes): This works because we manually override the
    # ReturnSubscriptionArn field in SubscribeInput to "true"
    assert 'status' in cr
    assert 'ackResourceMetadata' in cr['status']
    assert 'arn' in cr['status']['ackResourceMetadata']
    sub_arn = cr['status']['ackResourceMetadata']['arn']

    yield (ref, cr, sub_arn)

    _, deleted = k8s.delete_custom_resource(
        ref,
        period_length=DELETE_SUBSCRIPTION_TIMEOUT_SECONDS,
    )
    assert deleted

    subscription.wait_until_deleted(sub_arn)


@service_marker
@pytest.mark.canary
class TestSubscription:
    def test_crud(self, subscription_sqs):
        sub_ref, sub_cr, sub_arn = subscription_sqs

        subscription.wait_until_exists(sub_arn)

        condition.assert_synced(sub_ref)