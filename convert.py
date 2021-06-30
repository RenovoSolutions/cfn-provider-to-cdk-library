import json
import sys
import git
import argparse
import urllib.request
import tempfile
import os
import shutil
import re

def main():
  args = argument_parser(sys.argv[1:])
  with tempfile.TemporaryDirectory() as tmpdir:
    local_path = f'{tmpdir}/temp.json'
    print(f'INFO: Downloading from {args.schema_url}')
    urllib.request.urlretrieve(args.schema_url, local_path)
    f = open(local_path)

    print(f'INFO: Loading schema and converting.')
    data = json.load(f)

    result = {
      "ResourceTypes": {
        data["typeName"]: {
          "Attributes": {},
          "Properties": {}
        }
      }
    }

    for k, v in data['properties'].items():
      result["ResourceTypes"][data["typeName"]]["Attributes"][k] = {
        "PrimitiveType": v["type"].capitalize()
      }

      required = False
      if k in data["required"]:
        required = True

      update_type = "Mutable"
      if f"/properties/{k}" in data['createOnlyProperties']:
        update_type = "Immutable"

      result["ResourceTypes"][data["typeName"]]["Properties"][k] = {
        "PrimitiveType": v["type"].capitalize(),
        "Required": required,
        "UpdateType": update_type
      }

    print('INFO: Resulting spec:')
    print(json.dumps(result, indent=2))

    print('INFO: Cloning aws-cdk repo')
    git.Git(tmpdir).clone('https://github.com/aws/aws-cdk.git')

    print('INFO: Running yarn install for aws-cdk repo')
    os.system(f'cd {tmpdir}/aws-cdk; yarn install')

    print('INFO: Running buildup on cfn2ts')
    os.system(f'cd {tmpdir}/aws-cdk/tools/cfn2ts; ../../scripts/buildup')

    print('INFO: Saving resource spec to cfnspec for patching.')
    save_path = f'{tmpdir}/aws-cdk/packages/@aws-cdk/cfnspec/spec-source/999_result.json'
    with open(save_path, 'w') as outfile:
      json.dump(result, outfile, indent=2)

    print('INFO: Running cfnspec bump to patch in custom resource.')
    os.system(f'cd {tmpdir}/aws-cdk; ./scripts/bump-cfnspec.sh')

    print('INFO: Patching cfn2ts genspec to allow Generic prefix')
    genspec_lines = ''
    genspec_path = f'{tmpdir}/aws-cdk/tools/cfn2ts/lib/genspec.js'
    with open(genspec_path, 'r') as inputfile:
      genspec_lines = inputfile.readlines()
    with open(genspec_path, 'w') as outputfile:
      for line in genspec_lines:
        outputfile.write(re.sub(r"'AWS', 'Alexa'", "'AWS', 'Alexa', 'Generic'", line))

    data["typeName"]

    print('INFO: Generating typescript with cfn2ts')
    os.system(f'cd {tmpdir}/aws-cdk/tools/cfn2ts; bin/cfn2ts --scope {data["typeName"].rsplit("::", 1)[0]}')

    print('INFO: Copying final typescript')
    scope_name = data["typeName"].split("::")[1].lower()
    org_name = data["typeName"].split("::")[0].lower()
    shutil.copytree(f'{tmpdir}/aws-cdk/packages/@aws-cdk/{org_name}-{scope_name}', f'{args.output_path}/{org_name}-{scope_name}')
    shutil.copyfile(f'{tmpdir}/aws-cdk/tools/cfn2ts/lib/{scope_name}.generated.ts', f'{args.output_path}/{org_name}-{scope_name}/lib/{scope_name}.generated.ts')

def argument_parser(cli_args, validate=True):
  parser = argparse.ArgumentParser(description="Convert CloudFormation Resource Provider Schema files (new spec) to Resource Specification files (old spec) which can then be converted to a AWS CDK TypeScript library with cfn2ts")

  parser.add_argument('--schema-url', '-u', help='The target schema file to convert.', required=True, dest='schema_url')
  parser.add_argument('--output-path', '-o', help='The output path.', default='./', dest='output_path')

  args, discard = parser.parse_known_args(cli_args)

  return args

if __name__ == "__main__":
  main()
