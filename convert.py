import json
import sys
import git
import argparse
import urllib.request
import tempfile
import os
import shutil
import re

def copy_and_overwrite(from_path, to_path):
    if os.path.exists(to_path):
        shutil.rmtree(to_path)
    shutil.copytree(from_path, to_path)

def main():
  args = argument_parser(sys.argv[1:])
  with tempfile.TemporaryDirectory() as tmpdir:
    local_path = f'{tmpdir}/temp.json'
    print(f'INFO: Downloading from {args.schema_url}')
    urllib.request.urlretrieve(args.schema_url, local_path)
    f = open(local_path)

    print(f'INFO: Loading schema and converting.')
    data = json.load(f)

    scope_name = data["typeName"].split("::")[1].lower()
    org_name = data["typeName"].split("::")[0].lower()

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

    print(f'INFO: Patching cfn2ts genspec to allow {org_name.capitalize()} prefix')
    genspec_lines = ''
    genspec_path = f'{tmpdir}/aws-cdk/tools/cfn2ts/lib/genspec.js'
    with open(genspec_path, 'r') as inputfile:
      genspec_lines = inputfile.readlines()
    with open(genspec_path, 'w') as outputfile:
      for line in genspec_lines:
        outputfile.write(re.sub(r"'AWS', 'Alexa'", f"'AWS', 'Alexa', '{org_name.capitalize()}'", line))

    print('INFO: Generating typescript with cfn2ts')
    os.system(f'cd {tmpdir}/aws-cdk/tools/cfn2ts; bin/cfn2ts --scope {data["typeName"].rsplit("::", 1)[0]}')

    print('INFO: Copying generated ts to package folder')
    shutil.copyfile(f'{tmpdir}/aws-cdk/tools/cfn2ts/lib/{scope_name}.generated.ts', f'{tmpdir}/aws-cdk/packages/@aws-cdk/{org_name}-{scope_name}/lib/{scope_name}.generated.ts')

    # print('INFO: Building package')
    # os.system(f'cd {tmpdir}/aws-cdk/packages/@aws-cdk/{org_name}-{scope_name}; ../../../scripts/buildup')

    print('INFO: Copying final package')
    final_package_path = f'{args.output_path}/{data["typeName"].replace("::", "-").lower()}'
    copy_and_overwrite(f'{tmpdir}/aws-cdk/packages/@aws-cdk/{org_name}-{scope_name}', final_package_path)

    print('INFO: Will replace package.json in final package')
    package_name = data["typeName"].replace("::", "-").lower()
    if not args.npmscope == None:
      package_name = f'{args.npmscope}/{data["typeName"].replace("::", "-").lower()}'

    packagejson = {
      "name": package_name,
      "version": args.version,
      "description": f"The CDK Construct Library for {data['typeName']}",
      "main": "dist/index.js",
      "types": "dist/index.d.ts",
      "directories": {
        "lib": "lib",
        "test": "test"
      },
      "scripts": {
        "test": "echo \"Error: no test specified\" && exit 1"
      },
      "author": args.author,
      "license": "",
      "dependencies": {
        "@aws-cdk/core": args.cdkver
      }
    }
    with open(f'{final_package_path}/package.json', 'w') as outfile:
      json.dump(packagejson, outfile, indent=2)
    
    print('INFO: Generating tsconfig')
    tsconfig = {
      "compilerOptions": {
        "target": "ES2017",
        "module": "commonjs",
        "declaration": True,
        "outDir": "./dist",
        "strict": True,
        "esModuleInterop": True,
        "skipLibCheck": True,
        "forceConsistentCasingInFileNames": True
      }
    }
    with open(f'{final_package_path}/tsconfig.json', 'w') as outfile:
      json.dump(tsconfig, outfile, indent=2)

    print('INFO: Cleaning up unused files')
    shutil.rmtree(f'{final_package_path}/test')
    os.remove(f'{final_package_path}/LICENSE')
    os.remove(f'{final_package_path}/NOTICE')
    os.remove(f'{final_package_path}/jest.config.js')
    os.remove(f'{final_package_path}/.eslintrc.js')

def argument_parser(cli_args, validate=True):
  parser = argparse.ArgumentParser(description="Convert CloudFormation Resource Provider Schema files (new spec) to Resource Specification files (old spec) which can then be converted to a AWS CDK TypeScript library with cfn2ts")

  parser.add_argument('--schema-url', '-u', help='The target schema file to convert.', required=True, dest='schema_url')
  parser.add_argument('--output-path', '-o', help='The output path.', default='./', dest='output_path')
  parser.add_argument('--version', help='Version of the output package', default='0.1.0', dest='version')
  parser.add_argument('--author', help='Package author', default='', dest='author')
  parser.add_argument('--cdk-version', help='CDK package version for final package', default='^1.110.1', dest='cdkver')
  parser.add_argument('--npm-scope', help='The npm registry user or organization scope', default=None, dest='npmscope')

  args, discard = parser.parse_known_args(cli_args)

  return args

if __name__ == "__main__":
  main()
