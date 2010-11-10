import argparse
import os
import subprocess
import urllib2

from gondor.http import MultipartPostHandler


def cmd_deploy(args):
    domain = args.domain[0]
    commit = args.commit[0]
    
    tarball = None
    
    try:
        print "building tarball from %s" % commit
        
        tarball = os.path.abspath(os.path.join(os.curdir, "%s.tar.gz" % domain))
        cmd = "git archive --format=tar %s | gzip > %s" % (commit, tarball)
        subprocess.call([cmd], shell=True)
        
        print "pushing tarball to Gondor for deploy"
        
        opener = urllib2.build_opener(MultipartPostHandler)
        params = {
            "domain": domain,
            "tarball": open(tarball, "rb"),
        }
        print opener.open("http://gondor.eldarion.com/deploy/", params).read()
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
    