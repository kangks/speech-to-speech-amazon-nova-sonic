import * as cdk from 'aws-cdk-lib';
import { aws_ec2 as ec2 } from 'aws-cdk-lib';
import { aws_ecr as ecr } from 'aws-cdk-lib';
import { aws_ecs as ecs } from 'aws-cdk-lib';
import { aws_ecs_patterns as ecsPatterns } from 'aws-cdk-lib';
import { aws_route53 as route53 } from 'aws-cdk-lib';
import { aws_route53_targets as route53Targets } from 'aws-cdk-lib';
import { aws_ssm as ssm } from 'aws-cdk-lib';
import { aws_certificatemanager as acm } from 'aws-cdk-lib';
import { aws_elasticloadbalancingv2 as elbv2 } from 'aws-cdk-lib';
import { aws_ecr_assets as ecr_assets } from 'aws-cdk-lib';
import * as fs from 'fs';
import * as path from 'path';
import { Construct } from 'constructs';

interface DnsConfig {
  domainName: string;
  webappSubdomain: string;
  apiSubdomain: string;
  webappCertificateArn: string;
  apiCertificateArn: string;
}

export class CdkStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);
    
    // Add tags to all resources in the stack
    cdk.Tags.of(this).add('Project', 'NovaSonic');
    cdk.Tags.of(this).add('Environment', 'POC');
    cdk.Tags.of(this).add('ManagedBy', 'CDK');

    // Load DNS configuration
    const dnsConfigPath = path.join(__dirname, '..', 'dns-config.json');
    const dnsConfig: DnsConfig = JSON.parse(fs.readFileSync(dnsConfigPath, 'utf8'));

    // Create VPC
    const vpc = new ec2.Vpc(this, 'NovaVpc', {
      maxAzs: 2,
      natGateways: 1,
    });

    // Create ECS Cluster
    const cluster = new ecs.Cluster(this, 'NovaCluster', {
      vpc,
      containerInsights: true,
    });

    // Load environment variables from .env file
    const envFilePath = path.join(__dirname, '../../server/.env');
    const envVars: Record<string, string> = {};
    const secretVars: Record<string, string> = {};
    
    if (fs.existsSync(envFilePath)) {
      const envFileContent = fs.readFileSync(envFilePath, 'utf8');
      envFileContent.split('\n').forEach(line => {
        const match = line.match(/^([^#=]+)=(.*)$/);
        if (match) {
          const key = match[1].trim();
          const value = match[2].trim();
          // Separate secrets from regular environment variables
          if (['DAILY_API_KEY', 'NOVA_AWS_SECRET_ACCESS_KEY', 'NOVA_AWS_ACCESS_KEY_ID'].includes(key)) {
            secretVars[key] = value;
          } else {
            envVars[key] = value;
          }
        }
      });
    }
    
    // Create Parameter Store parameters for secrets
    const parameterStore: Record<string, ssm.StringParameter> = {};
    Object.entries(secretVars).forEach(([key, value]) => {
      parameterStore[key] = new ssm.StringParameter(this, `${key}Parameter`, {
        parameterName: `/nova-sonic/${key}`,
        stringValue: value,
        description: `Secret parameter for ${key}`,
      });
    });

    // Find hosted zone
    const hostedZone = route53.HostedZone.fromLookup(this, 'HostedZone', {
      domainName: dnsConfig.domainName,
    });

    // Import certificates
    const apiCertificate = acm.Certificate.fromCertificateArn(
      this, 'ApiCertificate', dnsConfig.apiCertificateArn
    );
    
    const webappCertificate = acm.Certificate.fromCertificateArn(
      this, 'WebappCertificate', dnsConfig.webappCertificateArn
    );

    // Create Python Server Construct
    this.createPythonServerConstruct(
      cluster,
      dnsConfig,
      hostedZone,
      apiCertificate,
      envVars,
      parameterStore
    );

    // Create Vite Web App Construct
    this.createViteWebAppConstruct(
      cluster,
      dnsConfig,
      hostedZone,
      webappCertificate
    );
  }

  private createPythonServerConstruct(
    cluster: ecs.ICluster,
    dnsConfig: DnsConfig,
    hostedZone: route53.IHostedZone,
    certificate: acm.ICertificate,
    envVars: Record<string, string>,
    parameterStore: Record<string, ssm.StringParameter>
  ): ecsPatterns.ApplicationLoadBalancedFargateService {
    // Build container image from local Dockerfile
    const serverImage = new ecr_assets.DockerImageAsset(this, 'ServerImage', {
      directory: path.join(__dirname, '../../server'),
      platform: cdk.aws_ecr_assets.Platform.LINUX_AMD64,
    });

    // Create Fargate service with ALB
    const serverService = new ecsPatterns.ApplicationLoadBalancedFargateService(this, 'ServerService', {
      cluster,
      memoryLimitMiB: 2048,
      cpu: 1024,
      desiredCount: 1,
      taskImageOptions: {
        image: ecs.ContainerImage.fromDockerImageAsset(serverImage),        
        containerPort: 8000,
        environment: {
          ...envVars,
          HOST: '0.0.0.0',
          PORT: '8000',
        },
        secrets: {
          // Load secrets from Parameter Store
          DAILY_API_KEY: ecs.Secret.fromSsmParameter(
            parameterStore['DAILY_API_KEY']
          ),
          NOVA_AWS_SECRET_ACCESS_KEY: ecs.Secret.fromSsmParameter(
            parameterStore['NOVA_AWS_SECRET_ACCESS_KEY']
          ),
          NOVA_AWS_ACCESS_KEY_ID: ecs.Secret.fromSsmParameter(
            parameterStore['NOVA_AWS_ACCESS_KEY_ID']
          ),
        },
        logDriver: new ecs.AwsLogDriver({
          streamPrefix: 'nova-server',
        }),
      },
      runtimePlatform: {
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
        cpuArchitecture: ecs.CpuArchitecture.X86_64, // Use X86_64
      },
      publicLoadBalancer: true,
      certificate,
      domainName: `${dnsConfig.apiSubdomain}.${dnsConfig.domainName}`,
      domainZone: hostedZone,
      redirectHTTP: true,
      healthCheckGracePeriod: cdk.Duration.seconds(60),
    });

    // Configure health check
    serverService.targetGroup.configureHealthCheck({
      path: '/health',
      interval: cdk.Duration.seconds(60),
      timeout: cdk.Duration.seconds(5),
      healthyThresholdCount: 2,
      unhealthyThresholdCount: 5,
      healthyHttpCodes: '200,201,202,203,204,301,302,303,304',
      port: '8000',
    });

    return serverService;
  }

  private createViteWebAppConstruct(
    cluster: ecs.ICluster,
    dnsConfig: DnsConfig,
    hostedZone: route53.IHostedZone,
    certificate: acm.ICertificate
  ): ecsPatterns.ApplicationLoadBalancedFargateService {
    // Build container image from local Dockerfile
    const webappImage = new ecr_assets.DockerImageAsset(this, 'WebappImage', {
      directory: path.join(__dirname, '../../vite-client'),
      platform: cdk.aws_ecr_assets.Platform.LINUX_ARM64,
    });

    // Create Fargate service with ALB
    const webappService = new ecsPatterns.ApplicationLoadBalancedFargateService(this, 'WebappService', {
      cluster,
      memoryLimitMiB: 512,
      cpu: 256,
      desiredCount: 2,
      
      taskImageOptions: {
        image: ecs.ContainerImage.fromDockerImageAsset(webappImage),
        containerPort: 80,
        environment: {
          // Set API endpoint for the web app
          SONIC_APP_API_ENDPOINT: `https://${dnsConfig.apiSubdomain}.${dnsConfig.domainName}`,
        },
        logDriver: new ecs.AwsLogDriver({
          streamPrefix: 'nova-webapp',
        }),
      },
      runtimePlatform: {
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
        cpuArchitecture: ecs.CpuArchitecture.ARM64
      },
      publicLoadBalancer: true,
      certificate,
      domainName: `${dnsConfig.webappSubdomain}.${dnsConfig.domainName}`,
      domainZone: hostedZone,
      redirectHTTP: true,
    });

    // Configure health check
    webappService.targetGroup.configureHealthCheck({
      path: '/',
      interval: cdk.Duration.seconds(60),
      timeout: cdk.Duration.seconds(5),
      healthyThresholdCount: 2,
      unhealthyThresholdCount: 5,
      healthyHttpCodes: '200,301,302',
      port: '80',
    });

    return webappService;
  }
}
