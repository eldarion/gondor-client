import argparse


def cmd_deploy(args):
    pass


def main():
    parser = argparse.ArgumentParser(prog="gondor")
    command_parsers = parser.add_subparsers(dest="command")
    
    # cmd: deploy
    parser_deploy = command_parsers.add_parser("deploy")
    parser_deploy.add_argument("domain", nargs=1)
    
    args = parser.parse_args()
    if args.command == "deploy":
        cmd_deploy(args)
    