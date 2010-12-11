import argparse
import ConfigParser
import os
import subprocess
import sys
import urllib2
import zlib

from gondor import http, utils


def cmd_deploy(args, config):
    domain = args.domain[0]
    commit = args.commit[0]
    
    tarball = None
    
    try:
        sys.stdout.write("Building tarball from %s... " % commit)
        repo_root = utils.check_output("git rev-parse --show-toplevel").strip()
        tarball = os.path.abspath(os.path.join(repo_root, "%s.tar.gz" % domain))
        cmd = "(cd %s && git archive --format=tar %s | gzip > %s)" % (repo_root, commit, tarball)
        subprocess.call([cmd], shell=True)
        sys.stdout.write("[ok]\n")
        
        text = "Pushing tarball to Gondor... "
        sys.stdout.write(text)
        url = "http://gondor.eldarion.com/deploy/"
        mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
        mgr.add_password(None, url, config["username"], config["password"])
        opener = urllib2.build_opener(
            urllib2.HTTPBasicAuthHandler(mgr),
            http.MultipartPostHandler,
            http.UploadProgressHandler
        )
        params = {
            "domain": domain,
            "tarball": open(tarball, "rb"),
        }
        response = opener.open(url, params)
        sys.stdout.write("\r%s[%s]   \n" % (text, response.read()))
    finally:
        if tarball:
            os.unlink(tarball)


def cmd_sqldump(args, config):
    domain = args.domain[0]
    
    # request SQL dump and stream the response through uncompression
    
    d = zlib.decompressobj(16+zlib.MAX_WBITS)
    sql_url = "http://gondor.eldarion.com/sqldump/%s" % domain
    mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, sql_url, config["username"], config["password"])
    opener = urllib2.build_opener(urllib2.HTTPBasicAuthHandler(mgr))
    response = opener.open(sql_url)
    cs = 16 * 1024
    while True:
        chunk = response.read(cs)
        if not chunk:
            break
        sys.stdout.write(d.decompress(chunk))
        sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(prog="gondor")
    command_parsers = parser.add_subparsers(dest="command")
    
    # cmd: deploy
    parser_deploy = command_parsers.add_parser("deploy")
    parser_deploy.add_argument("domain", nargs=1)
    parser_deploy.add_argument("commit", nargs=1)
    
    # cmd: sqldump
    parser_sqldump = command_parsers.add_parser("sqldump")
    parser_sqldump.add_argument("domain", nargs=1)
    
    args = parser.parse_args()
    
    # config
    
    config = ConfigParser.RawConfigParser()
    config.read(os.path.expanduser("~/.gondor"))
    config = {
        "username": config.get("auth", "username"),
        "password": config.get("auth", "password"),
        "api_key": config.get("auth", "key"),
    }
    
    {
        "deploy": cmd_deploy,
        "sqldump": cmd_sqldump
    }[args.command](args, config)
    