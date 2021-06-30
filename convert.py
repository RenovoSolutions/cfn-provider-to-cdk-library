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

# with open('resource.ts', 'w') as outfile:
#   resource_name = data['typeName'].replace("::", "")
#   cfn_class = f"Cfn{resource_name}"

#   outfile.write("import * as cdk from '@aws-cdk/core';\nimport * as cfn_parse from '@aws-cdk/core/lib/cfn-parse';\n\n")

#   # Start props
#   outfile.write(f"export interface {cfn_class}Props {{\n")

#   # Add all props
#   for k, v in data['properties'].items():
#     prop_name = k
#     prop_type = v['type']
#     if prop_type == 'integer':
#       prop_type = 'number'

#     optional = '?'
#     if prop_name in data['required']:
#       optional = ''

#     outfile.write(f"    /**\n    * `{data['typeName']}.{prop_name}`.\n    *\n    * @external\n    */\n")
#     outfile.write(f"    {prop_name[0].lower() + prop_name[1:]}{optional}: {prop_type};\n")

#   # Close props
#   outfile.write("}\n")

#   # Add Cfn class
#   outfile.write(f"export declare class {cfn_class} extends cdk.CfnResource implements cdk.IInspectable {{\n")

#   # Set type name in CFN
#   outfile.write("    /**\n     * The CloudFormation resource type name for this resource class.\n     *\n     * @external\n     */\n")
#   outfile.write(f'    static readonly CFN_RESOURCE_TYPE_NAME = "{data["typeName"]}";\n')

#   # Allow working with the cloudformation-include module
#   outfile.write("    /**\n     * @internal\n     */\n")
#   outfile.write(f"    static _fromCloudFormation(scope: cdk.Construct, id: string, resourceAttributes: any, options: cfn_parse.FromCloudFormationOptions): {cfn_class};\n")

#   # Add readonly attributes
#   for prop in data['readOnlyProperties']:
#     prop_name = prop.rsplit("/", 1)[1]
#     prop_type = data['properties'][prop_name]['type']
#     if prop_type == 'integer':
#       prop_type = 'number'

#     outfile.write(f"    /**\n    * @external\n    * @cloudformationAttribute {prop_name}\n    */\n")
#     outfile.write(f"    readonly attr{prop_name}: {prop_type};\n")

#   # Add all properties
#   for k, v in data['properties'].items():
#     prop_name = k
#     prop_type = v['type']
#     if prop_type == 'integer':
#       prop_type = 'number'

#     optional = ' | undefined'
#     if prop_name in data['required']:
#       optional = ''

#     outfile.write(f"    /**\n    * `{data['typeName']}.{prop_name}`.\n    *\n    * @external\n    */\n")
#     outfile.write(f"    {prop_name[0].lower() + prop_name[1:]}: {prop_type}{optional};\n")

#   # Add props inspector
#   outfile.write(f"    /**\n    * Create a new `Renovo::Vault::Secret`.\n    *\n    * @param scope - scope in which this resource is defined.\n    * @param id - scoped id of the resource.\n    * @param props - resource properties.\n    * @external\n    */\n")
#   outfile.write(f"    constructor(scope: cdk.Construct, id: string, props?: CfnRenovoVaultSecretProps);\n")
#   outfile.write(f"    /**\n    * Examines the CloudFormation resource and discloses attributes.\n    *\n    * @param inspector - tree inspector to collect and process attributes.\n    * @external\n    */\n")
#   outfile.write(f"    inspect(inspector: cdk.TreeInspector): void;\n")
#   outfile.write(f"    /**\n    * @external\n    */\n")
#   outfile.write(f"    protected get cfnProperties(): {{\n        [key: string]: any;\n    }};\n")
#   outfile.write(f"    /**\n    * @external\n    */\n")
#   outfile.write(f"    protected renderProperties(props: {{\n        [key: string]: any;\n    }}): {{\n        [key: string]: any;\n    }};\n")

#   # Close class
#   outfile.write("}")
