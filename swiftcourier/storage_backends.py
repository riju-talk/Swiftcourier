"""Optional S3 storage backends.

NOT wired up by default - settings.py configures S3 media via
STORAGES["default"] + AWS_* settings instead (see the "Storage" section).
Kept for the case where you want static and media on separate prefixes/buckets.

They deliberately do NOT set default_acl: modern S3 buckets have ACLs disabled
("Bucket owner enforced"), so an object-level ACL raises
AccessControlListNotSupported - use a bucket policy for public read instead.
"""

from storages.backends.s3boto3 import S3Boto3Storage


class StaticStorage(S3Boto3Storage):
    location = "static"


class MediaStorage(S3Boto3Storage):
    location = "media"
