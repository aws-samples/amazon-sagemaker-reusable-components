
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import os
import json
import boto3

def get_environment(ssm_params):
    sm = boto3.client("sagemaker")
    ssm = boto3.client("ssm")

    r = sm.describe_domain(
            DomainId=[
                d["DomainId"] for d in sm.list_domains()["Domains"] if boto3.Session().region_name in d["DomainArn"]
            ][0]
        )
    del r["ResponseMetadata"]
    del r["CreationTime"]
    del r["LastModifiedTime"]
    r = {**r, **r["DefaultUserSettings"]}
    del r["DefaultUserSettings"]

    i = {
        **r,
        **{t["Key"]:t["Value"] 
            for t in sm.list_tags(ResourceArn=r["DomainArn"])["Tags"] 
            if t["Key"] in ["EnvironmentName", "EnvironmentType"]}
    }

    for p in ssm_params:
        try:
            i[p["VariableName"]] = ssm.get_parameter(Name=f"{i['EnvironmentName']}-{i['EnvironmentType']}-{p['ParameterName']}")["Parameter"]["Value"]
        except:
            i[p["VariableName"]] = ""

    return i