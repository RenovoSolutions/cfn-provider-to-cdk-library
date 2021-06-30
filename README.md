# cfn-provider-to-cdk-library

- Create a virtual environment `python3 -m venv venv` and activate it `source venv/bin/activate`
- Install requirements `pip install -r requirements.txt`
- Run `python3 convert.py --schema-url <url>` where the URL is the provider JSON schema file for a Cloudformation Registry resource. This python code will convert that provider schema to a CDK typescript library using `cfn2ts` from the aws-cdk tools in the aws-cdk code repo.

This is hacky. Results not guaranteed. Currently doesn't support a locally stored schema but could easily be converted to do so.
