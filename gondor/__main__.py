import argparse
import ConfigParser
import os
import subprocess
import sys
import urllib
import urllib2
import zlib

try:
    import simplejson as json
except ImportError:
    import json

from gondor import __version__
from gondor import http, utils


def cmd_init(args, config):
    # ensure os.getcwd() is a Django directory
    files = [
        os.path.join(os.getcwd(), "__init__.py"),
        os.path.join(os.getcwd(), "manage.py")
    ]
    if not all([os.path.exists(f) for f in files]):
        sys.stderr.write("You must run gondor init from a Django project directory.\n")
        sys.exit(1)
    
    gondor_dir = os.path.abspath(os.path.join(os.getcwd(), os.pardir, ".gondor"))
    
    if not os.path.exists(gondor_dir):
        os.mkdir(gondor_dir)
        
        # write out a .gondor/config INI file
        new_config = ConfigParser.RawConfigParser()
        new_config.add_section("gondor")
        new_config.set("gondor", "site_key", args.site_key[0])
        with open(os.path.join(gondor_dir, "config"), "wb") as cf:
            new_config.write(cf)


def cmd_deploy(args, config):
    label = args.label[0]
    commit = args.commit[0]
    
    gondor_dirname = ".gondor"
    repo_root = utils.find_nearest(os.getcwd(), gondor_dirname)
    tarball = None
    
    try:
        sys.stdout.write("Reading configuration... ")
        local_config = ConfigParser.RawConfigParser()
        local_config.read(os.path.join(repo_root, gondor_dirname, "config"))
        client_key = local_config.get("gondor", "site_key")
        sys.stdout.write("[ok]\n")
        
        sha = utils.check_output("git rev-parse %s" % commit).strip()
        if commit == "HEAD":
            commit = sha
        
        sys.stdout.write("Building tarball from %s... " % commit)
        tarball = os.path.abspath(os.path.join(repo_root, "%s-%s.tar.gz" % (label, sha)))
        cmd = "(cd %s && git archive --format=tar %s | gzip > %s)" % (repo_root, commit, tarball)
        subprocess.call([cmd], shell=True)
        sys.stdout.write("[ok]\n")
        
        text = "Pushing tarball to Gondor... "
        sys.stdout.write(text)
        url = "http://gondor.io/deploy/"
        mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
        mgr.add_password(None, url, config["username"], config["password"])
        opener = urllib2.build_opener(
            urllib2.HTTPBasicAuthHandler(mgr),
            http.MultipartPostHandler,
            http.UploadProgressHandler
        )
        params = {
            "version": __version__,
            "site_key": client_key,
            "label": label,
            "sha": sha,
            "commit": commit,
            "tarball": open(tarball, "rb"),
        }
        response = opener.open(url, params)
        data = json.loads(response.read())
        if data["status"] == "error":
            message = data["message"]
        elif data["status"] == "success":
            message = "ok"
        else:
            message = "unknown"
        sys.stdout.write("\r%s[%s]   \n" % (text, message))
    finally:
        if tarball:
            os.unlink(tarball)


def cmd_sqldump(args, config):
    label = args.label[0]
    
    gondor_dirname = ".gondor"
    repo_root = utils.find_nearest(os.getcwd(), gondor_dirname)
    
    local_config = ConfigParser.RawConfigParser()
    local_config.read(os.path.join(repo_root, gondor_dirname, "config"))
    client_key = local_config.get("gondor", "site_key")
    
    # request SQL dump and stream the response through uncompression
    
    d = zlib.decompressobj(16+zlib.MAX_WBITS)
    sql_url = "http://gondor.io/sqldump/"
    mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, sql_url, config["username"], config["password"])
    opener = urllib2.build_opener(urllib2.HTTPBasicAuthHandler(mgr))
    params = {
        "version": __version__,
        "site_key": client_key,
        "label": label,
    }
    response = opener.open(sql_url, urllib.urlencode(params))
    cs = 16 * 1024
    while True:
        chunk = response.read(cs)
        if not chunk:
            break
        sys.stdout.write(d.decompress(chunk))
        sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(prog="gondor")
    parser.add_argument("--version", action="version", version="%%(prog)s %s" % __version__)
    
    command_parsers = parser.add_subparsers(dest="command")
    
    # cmd: init
    parser_init = command_parsers.add_parser("init")
    parser_init.add_argument("site_key", nargs=1)
    
    # cmd: deploy
    parser_deploy = command_parsers.add_parser("deploy")
    parser_deploy.add_argument("label", nargs=1)
    parser_deploy.add_argument("commit", nargs=1)
    
    # cmd: sqldump
    parser_sqldump = command_parsers.add_parser("sqldump")
    parser_sqldump.add_argument("label", nargs=1)
    
    args = parser.parse_args()
    
    # config
    
    config = ConfigParser.RawConfigParser()
    config.read(os.path.expanduser("~/.gondor"))
    config = {
        "username": config.get("auth", "username"),
        "password": config.get("auth", "password"),
    }
    
    {
        "init": cmd_init,
        "deploy": cmd_deploy,
        "sqldump": cmd_sqldump
    }[args.command](args, config)
