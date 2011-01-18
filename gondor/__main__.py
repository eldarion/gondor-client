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
    site_key = args.site_key[0]
    if len(site_key) < 11:
        sys.stderr.write("The site key given is too short.\n")
        sys.exit(1)
    
    # ensure os.getcwd() is a Django directory
    files = [
        os.path.join(os.getcwd(), "__init__.py"),
        os.path.join(os.getcwd(), "manage.py")
    ]
    if not all([os.path.exists(f) for f in files]):
        sys.stderr.write("You must run gondor init from a Django project directory.\n")
        sys.exit(1)
    
    gondor_dir = os.path.abspath(os.path.join(os.getcwd(), ".gondor"))
    
    if not os.path.exists(gondor_dir):
        os.mkdir(gondor_dir)
        
        # write out a .gondor/config INI file
        new_config = ConfigParser.RawConfigParser()
        new_config.add_section("gondor")
        new_config.set("gondor", "site_key", site_key)
        new_config.set("gondor", "vcs", "git")
        with open(os.path.join(gondor_dir, "config"), "wb") as cf:
            new_config.write(cf)


def cmd_create(args, config):
    gondor_dirname = ".gondor"
    try:
        project_root = utils.find_nearest(os.getcwd(), gondor_dirname)
    except OSError:
        sys.stderr.write("Unable to find a .gondor directory.\n")
        sys.exit(1)
    
    label = args.label[0]
    
    kind = args.kind
    if kind is None:
        kind = "dev"
    
    sys.stdout.write("Reading configuration... ")
    local_config = ConfigParser.RawConfigParser()
    local_config.read(os.path.join(project_root, gondor_dirname, "config"))
    site_key = local_config.get("gondor", "site_key")
    sys.stdout.write("[ok]\n")
    
    text = "Creating instance on Gondor... "
    url = "http://api.gondor.io/create/"
    mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, url, config["username"], config["password"])
    opener = urllib2.build_opener(urllib2.HTTPBasicAuthHandler(mgr))
    params = {
        "version": __version__,
        "site_key": site_key,
        "label": label,
        "kind": kind,
        "project_root": os.path.basename(project_root),
    }
    response = opener.open(url, urllib.urlencode(params))
    data = json.loads(response.read())
    if data["status"] == "error":
        message = "error"
    elif data["status"] == "success":
        message = "ok"
    else:
        message = "unknown"
    sys.stdout.write("\r%s[%s]   \n" % (text, message))
    if data["status"] == "success":
        sys.stdout.write("\nRun: gondor deploy %s HEAD" % label)
        sys.stdout.write("\nVisit: %s\n" % data["url"])
    else:
        sys.stdout.write("\nError: %s\n" % data["message"])


def cmd_deploy(args, config):
    label = args.label[0]
    commit = args.commit[0]
    
    gondor_dirname = ".gondor"
    try:
        project_root = utils.find_nearest(os.getcwd(), gondor_dirname)
    except OSError:
        sys.stderr.write("Unable to find a .gondor directory.\n")
        sys.exit(1)
    
    tarball = None
    
    try:
        sys.stdout.write("Reading configuration... ")
        local_config = ConfigParser.RawConfigParser()
        local_config.read(os.path.join(project_root, gondor_dirname, "config"))
        site_key = local_config.get("gondor", "site_key")
        vcs = local_config.get("gondor", "vcs")
        sys.stdout.write("[ok]\n")
        
        if vcs == "git":
            try:
                repo_root = utils.find_nearest(os.getcwd(), ".git")
            except OSError:
                sys.stderr.write("Unable to find a .git directory.\n")
                sys.exit(1)
            sha = utils.check_output("git rev-parse %s" % commit).strip()
            if commit == "HEAD":
                commit = sha
            tarball = os.path.abspath(os.path.join(repo_root, "%s-%s.tar.gz" % (label, sha)))
            cmd = "(cd %s && git archive --format=tar %s | gzip > %s)" % (repo_root, commit, tarball)
        else:
            raise NotImplementedError()
        
        sys.stdout.write("Building tarball from %s... " % commit)
        subprocess.call([cmd], shell=True)
        sys.stdout.write("[ok]\n")
        
        text = "Pushing tarball to Gondor... "
        sys.stdout.write(text)
        url = "http://api.gondor.io/deploy/"
        mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
        mgr.add_password(None, url, config["username"], config["password"])
        opener = urllib2.build_opener(
            urllib2.HTTPBasicAuthHandler(mgr),
            http.MultipartPostHandler,
            http.UploadProgressHandler
        )
        params = {
            "version": __version__,
            "site_key": site_key,
            "label": label,
            "sha": sha,
            "commit": commit,
            "tarball": open(tarball, "rb"),
            "project_root": os.path.basename(project_root),
        }
        response = opener.open(url, params)
        data = json.loads(response.read())
        if data["status"] == "error":
            message = "error"
        elif data["status"] == "success":
            message = "ok"
        else:
            message = "unknown"
        sys.stdout.write("\r%s[%s]   \n" % (text, message))
        if data["status"] == "success":
            if "url" in data:
                sys.stdout.write("\nVisit: %s\n" % data["url"])
        else:
            sys.stdout.write("\nError: %s\n" % data["message"])
    finally:
        if tarball:
            os.unlink(tarball)


def cmd_sqldump(args, config):
    label = args.label[0]
    
    gondor_dirname = ".gondor"
    repo_root = utils.find_nearest(os.getcwd(), gondor_dirname)
    
    local_config = ConfigParser.RawConfigParser()
    local_config.read(os.path.join(repo_root, gondor_dirname, "config"))
    site_key = local_config.get("gondor", "site_key")
    
    # request SQL dump and stream the response through uncompression
    
    d = zlib.decompressobj(16+zlib.MAX_WBITS)
    sql_url = "http://api.gondor.io/sqldump/"
    mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, sql_url, config["username"], config["password"])
    opener = urllib2.build_opener(urllib2.HTTPBasicAuthHandler(mgr))
    params = {
        "version": __version__,
        "site_key": site_key,
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


def cmd_addon(args, config):
    
    addon_label = args.addon_label[0]
    instance_label = args.instance_label[0]
    
    gondor_dirname = ".gondor"
    try:
        project_root = utils.find_nearest(os.getcwd(), gondor_dirname)
    except OSError:
        sys.stderr.write("Unable to find a .gondor directory.\n")
        sys.exit(1)
    
    sys.stdout.write("Reading configuration... ")
    local_config = ConfigParser.RawConfigParser()
    local_config.read(os.path.join(project_root, gondor_dirname, "config"))
    site_key = local_config.get("gondor", "site_key")
    sys.stdout.write("[ok]\n")
    
    text = "Adding addon to your instance... "
    sys.stdout.write(text)
    url = "http://api.gondor.io/addon/"
    mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, url, config["username"], config["password"])
    opener = urllib2.build_opener(urllib2.HTTPBasicAuthHandler(mgr))
    params = {
        "version": __version__,
        "site_key": site_key,
        "addon_label": addon_label,
        "instance_label": instance_label,
    }
    response = opener.open(url, urllib.urlencode(params))
    data = json.loads(response.read())
    if data["status"] == "error":
        message = "error"
    elif data["status"] == "success":
        message = "ok"
    else:
        message = "unknown"
    sys.stdout.write("\r%s[%s]   \n" % (text, message))
    if data["status"] == "error":
        sys.stdout.write("\nError: %s\n" % data["message"])


def main():
    parser = argparse.ArgumentParser(prog="gondor")
    parser.add_argument("--version", action="version", version="%%(prog)s %s" % __version__)
    
    command_parsers = parser.add_subparsers(dest="command")
    
    # cmd: init
    parser_init = command_parsers.add_parser("init")
    parser_init.add_argument("site_key", nargs=1)
    
    # cmd: create
    parser_create = command_parsers.add_parser("create")
    parser_create.add_argument("--kind")
    parser_create.add_argument("label", nargs=1)
    
    # cmd: deploy
    parser_deploy = command_parsers.add_parser("deploy")
    parser_deploy.add_argument("label", nargs=1)
    parser_deploy.add_argument("commit", nargs=1)
    
    # cmd: sqldump
    parser_sqldump = command_parsers.add_parser("sqldump")
    parser_sqldump.add_argument("label", nargs=1)
    
    # cmd: addon
    parser_addon = command_parsers.add_parser("addon")
    parser_addon.add_argument("addon_label", nargs=1)
    parser_addon.add_argument("instance_label", nargs=1)
    
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
        "create": cmd_create,
        "deploy": cmd_deploy,
        "sqldump": cmd_sqldump,
        "addon": cmd_addon
    }[args.command](args, config)
