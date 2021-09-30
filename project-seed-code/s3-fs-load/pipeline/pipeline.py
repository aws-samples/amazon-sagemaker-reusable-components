# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import os
import json
import boto3
import logging
import sagemaker
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.parameters import (
    ParameterInteger,
    ParameterString,
)
from sagemaker.workflow.steps import ProcessingStep
from sagemaker.processing import (
    ProcessingInput, 
    ProcessingOutput,
    FeatureStoreOutput,
    Processor
)
from sagemaker.network import NetworkConfig
from sagemaker import image_uris

from utils import get_environment

logger = logging.getLogger(__name__)

def create_pipeline(
    pipeline_name="s3-fs-ingest-pipeline",
    pipeline_description="automated ingestion from s3 to feature store",
    project_id="",
    project_name="",
    data_wrangler_flow_s3_url="",
    flow_output_name="",
    input_data_s3_url="",
    feature_group_name="",
):
    logger.info(f"Creating sagemaker S3 to feature store load pipeline: {pipeline_name}")

    # get environment variables
    ssm_parameters = [
        {"VariableName":"PipelineExecutionRole", "ParameterName":"sm-pipeline-execution-role-arn"},
        {"VariableName":"DataBucketName", "ParameterName":"data-bucket-name"},
        {"VariableName":"S3KmsKeyId", "ParameterName":"kms-s3-key-arn"},
        {"VariableName":"EbsKmsKeyArn", "ParameterName":"kms-ebs-key-arn"},
    ]

    env_data = get_environment(ssm_params=ssm_parameters)
    logger.info(f"Retrieved environment data:\n{json.dumps(env_data, indent=2)}")

    sagemaker_session = sagemaker.Session(default_bucket=env_data["DataBucketName"])

    # setup pipeline parameters
    p_processing_instance_count = ParameterInteger(
        name="ProcessingInstanceCount",
        default_value=1
    )
    p_processing_instance_type = ParameterString(
        name="ProcessingInstanceType",
        default_value="ml.m5.4xlarge"
    )
    p_processing_volume_size = ParameterInteger(
        name="ProcessingVolumeSize",
        default_value=50
    )
    p_flow_output_name = ParameterString(
        name='FlowOutputName',
        default_value=flow_output_name
    )
    p_input_flow = ParameterString(
        name='InputFlowUrl',
        default_value=data_wrangler_flow_s3_url
    )
    p_input_data = ParameterString(
        name="InputDataUrl",
        default_value=input_data_s3_url
    )

    # DW flow processing job inputs and output
    flow_input = ProcessingInput(
        source=p_input_flow,
        destination="/opt/ml/processing/flow",
        input_name="flow",
        s3_data_type="S3Prefix",
        s3_input_mode="File",
        s3_data_distribution_type="FullyReplicated",
    )

    data_input = ProcessingInput(
        source=p_input_data,
        destination="/opt/ml/processing/data",
        input_name="data",
        s3_data_type="S3Prefix",
        s3_input_mode="File",
        s3_data_distribution_type="FullyReplicated"
    )

    processing_job_output = ProcessingOutput(
        output_name=p_flow_output_name,
        app_managed=True,
        feature_store_output=FeatureStoreOutput(feature_group_name=feature_group_name),
    )

    # get data wrangler container uri
    container_uri = image_uris.retrieve(
        framework='data-wrangler',
        region=sagemaker_session.boto_region_name
    )
 
    # set up network configuration
    network_config = NetworkConfig(
        enable_network_isolation=False, 
        security_group_ids=env_data["SecurityGroups"],
        subnets=env_data["SubnetIds"],
        encrypt_inter_container_traffic=True)

    logger.info(f"creating DW processor with container uri: {container_uri}")    
    
    # create DW processor
    processor = Processor(
        role=env_data["ExecutionRole"],
        image_uri=container_uri,
        instance_count=p_processing_instance_count,
        instance_type=p_processing_instance_type,
        volume_size_in_gb=p_processing_volume_size,
        sagemaker_session=sagemaker_session,
        network_config=network_config,
        volume_kms_key=env_data["EbsKmsKeyArn"],
        output_kms_key=env_data["S3KmsKeyId"]
    )

    step_process = ProcessingStep(
        name="datawrangler-processing-to-feature-store",
        processor=processor,
        inputs=[flow_input] + [data_input],
        outputs=[processing_job_output]
    )

    pipeline = Pipeline(
        name=pipeline_name,
        parameters=[
            p_processing_instance_type, 
            p_processing_instance_count,
            p_processing_volume_size,
            p_flow_output_name,
            p_input_flow,
            p_input_data,
        ],
        steps=[step_process],
        sagemaker_session=sagemaker_session
    )

    response = pipeline.upsert(
        role_arn=env_data["PipelineExecutionRole"],
        description=pipeline_description,
        tags=[
        {'Key': 'sagemaker:project-name', 'Value': project_name },
        {'Key': 'sagemaker:project-id', 'Value': project_id },
        {'Key': 'EnvironmentName', 'Value': env_data['EnvironmentName'] },
        {'Key': 'EnvironmentType', 'Value': env_data['EnvironmentType'] },
    ],
    )

    logger.info(f"pipeline upsert response: {response}")

    return pipeline