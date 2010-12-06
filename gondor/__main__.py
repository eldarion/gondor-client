import argparse
import os
import subprocess
import sys
import urllib2

from gondor import http


def cmd_deploy(args):
    domain = args.domain[0]
    commit = args.commit[0]
    
    tarball = None
    
    try:
        sys.stdout.write("Building tarball from %s... " % commit)
        tarball = os.path.abspath(os.path.join(os.curdir, "%s.tar.gz" % domain))
        cmd = "git archive --format=tar %s | gzip > %s" % (commit, tarball)
        subprocess.call([cmd], shell=True)
        sys.stdout.write("[ok]\n")
        
        text = "Pushing tarball to Gondor... "
        sys.stdout.write(text)
        opener = urllib2.build_opener(
            http.MultipartPostHandler,
            http.UploadProgressHandler
        )
        params = {
            "domain": domain,
            "tarball": open(tarball, "rb"),
        }
        response = opener.open("http://gondor.eldarion.com/deploy/", params)
        sys.stdout.write("\r%s[%s]   \n" % (text, response.read()))
    finally:
        if tarball:
            os.unlink(tarball)


def main():
    parser = argparse.ArgumentParser(prog="gondor")
    command_parsers = parser.add_subparsers(dest="command")
    
    # cmd: deploy
    parser_deploy = command_parsers.add_parser("deploy")
    parser_deploy.add_argument("domain", nargs=1)
    parser_deploy.add_argument("commit", nargs=1)
    
    args = parser.parse_args()
    if args.command == "deploy":
        cmd_deploy(args)
    