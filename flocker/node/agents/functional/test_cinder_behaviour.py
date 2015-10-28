# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Test for real world behaviour of Cinder implementations to validate some of our
basic assumptions/understandings of how Cinder works in the real world.
"""

from twisted.trial.unittest import SkipTest, SynchronousTestCase

from ..cinder import (
    get_keystone_session, get_cinder_v1_client, wait_for_volume_state,
    CinderBlockDeviceAPI, TimeoutException
)
from ..test.blockdevicefactory import (
    InvalidConfig,
    ProviderType,
    get_openstack_region_for_test,
    get_blockdevice_config,
)
from ....testtools import random_name

from uuid import uuid4
from ..blockdevice import BlockDeviceVolume


def cinder_volume_manager():
    """
    Get an ``ICinderVolumeManager`` configured to work on this environment.

    XXX: It will not automatically clean up after itself. See FLOC-1824.
    """
    try:
        config = get_blockdevice_config(ProviderType.openstack)
    except InvalidConfig as e:
        raise SkipTest(str(e))
    region = get_openstack_region_for_test()
    session = get_keystone_session(**config)
    return get_cinder_v1_client(session, region).volumes


def fakeGet(volume_id):
    """

    """
    return BlockDeviceVolume(
        size=100, attached_to=None,
        dataset_id=uuid4(),
        blockdevice_id=unicode(volume_id),
    )


# All of the following tests could be part of the suite returned by
# ``make_icindervolumemanager_tests`` instead.
# https://clusterhq.atlassian.net/browse/FLOC-1846

class VolumesCreateTests(SynchronousTestCase):
    """
    Tests for ``cinder.Client.volumes.create``.
    """
    def setUp(self):
        self.cinder_volumes = cinder_volume_manager()

    def test_create_metadata_is_listed(self):
        """
        ``metadata`` supplied when creating a volume is included when that
        volume is subsequently listed.
        """
        expected_metadata = {random_name(self): "bar"}

        new_volume = self.cinder_volumes.create(
            size=100,
            metadata=expected_metadata
        )
        self.addCleanup(self.cinder_volumes.delete, new_volume)
        listed_volume = wait_for_volume_state(
            volume_manager=self.cinder_volumes,
            expected_volume=new_volume,
            desired_state=u'available',
            transient_states=(u'creating',),
        )

        expected_items = set(expected_metadata.items())
        actual_items = set(listed_volume.metadata.items())
        missing_items = expected_items - actual_items
        self.assertEqual(
            set(), missing_items,
            'Metadata {!r} does not contain the expected items {!r}'.format(
                actual_items, expected_items
            )
        )


class VolumesSetMetadataTests(SynchronousTestCase):
    """
    Tests for ``cinder.Client.volumes.set_metadata``.
    """
    def setUp(self):
        self.cinder_volumes = cinder_volume_manager()

    def test_updated_metadata_is_listed(self):
        """
        ``metadata`` supplied to update_metadata is included when that
        volume is subsequently listed.
        """
        expected_metadata = {random_name(self): u"bar"}

        new_volume = self.cinder_volumes.create(size=100)
        self.addCleanup(self.cinder_volumes.delete, new_volume)

        listed_volume = wait_for_volume_state(
            volume_manager=self.cinder_volumes,
            expected_volume=new_volume,
            desired_state=u'available',
            transient_states=(u'creating',),
        )

        self.cinder_volumes.set_metadata(new_volume, expected_metadata)

        listed_volume = wait_for_volume_state(
            volume_manager=self.cinder_volumes,
            expected_volume=new_volume,
            desired_state=u'available',
        )

        expected_items = set(expected_metadata.items())
        actual_items = set(listed_volume.metadata.items())
        missing_items = expected_items - actual_items

        self.assertEqual(set(), missing_items)


class BlockDeviceAPIDestroyTests(SynchronousTestCase):
    """
    Test for ``cinder.CinderBlockDeviceAPI.destroy_volume``
    """
    def setUp(self):
        self.cinder_volumes = cinder_volume_manager()

    def test_destroy_timesout(self):
        """
        If the cinder cannot delete the volume, we should timeout
        after waiting some time
        """
        # Adding a fake get that will always return a volume, so we
        # timeout waiting for the volume to be deleted
        self.patch(self.cinder_volumes, "get", fakeGet)
        # Using a fake no-op delete so it doens't actually delete anything
        # (we don't need any actual volumes here, as we only need to verify
        # the timeout)
        self.patch(self.cinder_volumes, "delete", lambda *args, **kwargs: None)

        api = CinderBlockDeviceAPI(
            cinder_volume_manager=self.cinder_volumes,
            nova_volume_manager=object(),
            nova_server_manager=object(),
            cluster_id=uuid4()
            )
        # Setting the timeut to 1, as the default is quite high, and we do not
        # want to wait that much in a test
        api.timeout = 1
        self.assertRaises(
            TimeoutException,
            api.destroy_volume,
            blockdevice_id=unicode(uuid4())
        )
