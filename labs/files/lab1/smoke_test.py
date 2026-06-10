import boto3

print(boto3.client("sts").get_caller_identity()["Arn"])
for b in boto3.client("s3").list_buckets()["Buckets"]:
    print(b["Name"])
