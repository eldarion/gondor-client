import argparse
import ConfigParser
import getpass
import gzip
import os
import re
import stat
import subprocess
import sys
import tarfile
import time
import urllib
import urllib2
import webbrowser
import zlib

try:
    import simplejson as json
except ImportError:
    import json

from gondor import __version__
from gondor import http, utils
from gondor.api import make_api_call
from gondor.progressbar import ProgressBar


out = utils.out
err = utils.err
error = utils.error
api_error = utils.api_error


RE_VALID_USERNAME = re.compile('[\w.@+-]+$')
EMAIL_RE = re.compile(
    r"(^[-!#$%&'*+/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+/=?^_`{}|~0-9A-Z]+)*"  # dot-atom
    r'|^"([\001-\010\013\014\016-\037!#-\[\]-\177]|\\[\001-\011\013\014\016-\177])*"' # quoted-string
    r')@(?:[A-Z0-9-]+\.)+[A-Z]{2,6}$', # domain
    re.IGNORECASE)
DEFAULT_ENDPOINT = "https://api.gondor.io"


def config_value(config, section, key, default=None):
    try:
        return config.get(section, key)
    except (ConfigParser.NoOptionError, ConfigParser.NoSectionError):
        return default


def cmd_init(args, env, config):
    site_key = args.site_key[0]
    if len(site_key) < 11:
        error("The site key given is too short.\n")
    
    gondor_dir = os.path.abspath(os.path.join(os.getcwd(), ".gondor"))
    
    try:
        repo_root = utils.find_nearest(os.getcwd(), ".git")
    except OSError:
        try:
            repo_root = utils.find_nearest(os.getcwd(), ".hg")
        except OSError:
            error("unable to find a supported version control directory. Looked for .git and .hg.\n")
        else:
            vcs = "hg"
    else:
        vcs = "git"
    
    if not os.path.exists(gondor_dir):
        os.mkdir(gondor_dir)
        
        config_file = """[gondor]
site_key = %(site_key)s
vcs = %(vcs)s

[app]
; This path is relative to your project root (the directory .gondor is in)
requirements_file = requirements.txt

; The wsgi entry point of your application in two parts separated by a colon.
; wsgi:deploy where wsgi is the Python module which should be importable and
; application which represents the callable in the module.
wsgi_entry_point = wsgi:application

; Can be either nashvegas, south or none
migrations = none

; Whether or not to run collectstatic during deployment
staticfiles = off

; Whether or not to run compress (from django_compressor) during deployment
compressor = off

; Path to map frontend servers to for your site media (includes both STATIC_URL
; and MEDIA_URL; you must ensure they are under the same path)
site_media_url = /site_media

; The location of your manage.py. Gondor uses this as an entry point for
; management commands. This is relative to the directory .gondor lives in.
; managepy = manage.py

; Gondor will use settings_module as DJANGO_SETTINGS_MODULE when it runs your
; code. Commented out by default (means it will not be set).
; settings_module = settings
""" % {
    "site_key": site_key,
    "vcs": vcs
}
        
        out("Writing configuration (.gondor/config)... ")
        with open(os.path.join(gondor_dir, "config"), "wb") as cf:
            cf.write(config_file)
        out("[ok]\n")
         
        out("\nYou are now ready to deploy your project to Gondor. You might want to first\n")
        out("check .gondor/config (in this directory) for correct values for your\n")
        out("application. Once you are ready, run:\n\n")
        out("    gondor deploy primary %s\n" % {"git": "master", "hg": "default"}[vcs])
    else:
        out("Detecting existing .gondor/config. Not overriding.\n")


def cmd_create(args, env, config):
    
    label = args.label[0]
    
    kind = args.kind
    if kind is None:
        kind = "dev"
    
    text = "Creating instance on Gondor... "
    url = "%s/instance/create/" % config["gondor.endpoint"]
    params = {
        "version": __version__,
        "site_key": config["gondor.site_key"],
        "label": label,
        "kind": kind,
        "project_root": os.path.basename(env["project_root"]),
    }
    try:
        response = make_api_call(config, url, urllib.urlencode(params))
    except urllib2.HTTPError, e:
        api_error(e)
    data = json.loads(response.read())
    if data["status"] == "error":
        message = "error"
    elif data["status"] == "success":
        message = "ok"
    else:
        message = "unknown"
    out("\r%s[%s]   \n" % (text, message))
    if data["status"] == "success":
        out("\nRun: gondor deploy %s %s" % (label, {"git": "HEAD", "hg": "tip"}[config["gondor.vcs"]]))
        out("\nVisit: %s\n" % data["url"])
    else:
        error("%s\n" % data["message"])


def cmd_deploy(args, env, config):
    label = args.label[0]
    commit = args.commit[0]
    
    tar_path, tarball_path = None, None
    
    try:
        if config["gondor.vcs"] == "git":
            try:
                git = utils.find_command("git")
            except utils.BadCommand, e:
                error(e.args[0])
            check, sha = utils.run_proc([git, "rev-parse", commit])
            if check != 0:
                error("could not map '%s' to a SHA\n" % commit)
            if commit == "HEAD":
                commit = sha
            tar_path = os.path.abspath(os.path.join(env["repo_root"], "%s-%s.tar" % (label, sha)))
            cmd = [git, "archive", "--format=tar", commit, "-o", tar_path]
        elif config["gondor.vcs"] == "hg":
            try:
                hg = utils.find_command("hg")
            except utils.BadCommand, e:
                error(e.args[0])
            branches_stdout = utils.run_proc([hg, "branches"])[1]
            tags_stdout = utils.run_proc([hg, "tags"])[1]
            refs = {}
            for line in branches_stdout.splitlines() + tags_stdout.splitlines():
                m = re.search(r"([\w\d\.-]+)\s*([\d]+):([\w]+)$", line)
                if m:
                    refs[m.group(1)] = m.group(3)
            try:
                sha = refs[commit]
            except KeyError:
                error("could not map '%s' to a SHA\n" % commit)
            tar_path = os.path.abspath(os.path.join(env["repo_root"], "%s-%s.tar" % (label, sha)))
            cmd = [hg, "archive", "-p", ".", "-t", "tar", "-r", commit, tar_path]
        else:
            error("'%s' is not a valid version control system for Gondor\n" % config["gondor.vcs"])
        
        out("Archiving code from %s... " % commit)
        check, output = utils.run_proc(cmd, cwd=env["repo_root"])
        if check != 0:
            error(output)
        out("[ok]\n")
        
        tarball_path = os.path.abspath(os.path.join(env["repo_root"], "%s-%s.tar.gz" % (label, sha)))
        
        out("Building tarball... ")
        with open(tar_path, "rb") as tar_fp:
            try:
                tarball = gzip.open(tarball_path, mode="wb")
                tarball.writelines(tar_fp)
            finally:
                tarball.close()
        out("[ok]\n")
        
        pb = ProgressBar(0, 100, 77)
        out("Pushing tarball to Gondor... \n")
        url = "%s/instance/deploy/" % config["gondor.endpoint"]
        
        with open(tarball_path, "rb") as tarball:
            params = {
                "version": __version__,
                "site_key": config["gondor.site_key"],
                "label": label,
                "sha": sha,
                "commit": commit,
                "tarball": tarball,
                "project_root": os.path.relpath(env["project_root"], env["repo_root"]),
                "app": json.dumps(config["app"]),
            }
            handlers = [
                http.MultipartPostHandler,
                http.UploadProgressHandler(pb, ssl=True),
                http.UploadProgressHandler(pb, ssl=False)
            ]
            try:
                response = make_api_call(config, url, params, extra_handlers=handlers)
            except KeyboardInterrupt:
                out("\nCanceling uploading... [ok]\n")
                sys.exit(1)
            except urllib2.HTTPError, e:
                api_error(e)
            else:
                out("\n")
                data = json.loads(response.read())
    
    finally:
        if tar_path and os.path.exists(tar_path):
            os.unlink(tar_path)
        if tarball_path and os.path.exists(tarball_path):
            os.unlink(tarball_path)
    
    if data["status"] == "error":
        error("%s\n" % data["message"])
    if data["status"] == "success":
        deployment_id = data["deployment"]
        if "url" in data:
            instance_url = data["url"]
        else:
            instance_url = None
        
        # poll status of the deployment
        out("Deploying... ")
        while True:
            params = {
                "version": __version__,
                "site_key": config["gondor.site_key"],
                "instance_label": label,
                "task_id": deployment_id,
            }
            url = "%s/task/status/" % config["gondor.endpoint"]
            try:
                response = make_api_call(config, url, urllib.urlencode(params))
            except urllib2.URLError:
                # @@@ add max retries
                continue
            data = json.loads(response.read())
            if data["status"] == "error":
                out("[error]\n")
                error("%s\n" % data["message"])
            if data["status"] == "success":
                if data["state"] == "finished":
                    out("[ok]\n")
                    if instance_url:
                        out("\nVisit: %s\n" % instance_url)
                    break
                elif data["state"] == "failed":
                    out("[failed]\n")
                    out("\n%s\n" % data["reason"])
                    sys.exit(1)
                elif data["state"] == "locked":
                    out("[locked]\n")
                    out("\nYour deployment failed due to being locked. This means there is another deployment already in progress.\n")
                    sys.exit(1)
                else:
                    time.sleep(2)


def cmd_sqldump(args, env, config):
    label = args.label[0]
    
    # request SQL dump and stream the response through uncompression
    
    err("Dumping database... ")
    url = "%s/instance/sqldump/" % config["gondor.endpoint"]
    params = {
        "version": __version__,
        "site_key": config["gondor.site_key"],
        "label": label,
    }
    try:
        response = make_api_call(config, url, urllib.urlencode(params))
    except urllib2.HTTPError, e:
        api_error(e)
    data = json.loads(response.read())
    
    if data["status"] == "error":
        error("%s\n" % data["message"])
    if data["status"] == "success":
        task_id = data["task"]
        while True:
            params = {
                "version": __version__,
                "site_key": config["gondor.site_key"],
                "instance_label": label,
                "task_id": task_id,
            }
            url = "%s/task/status/" % config["gondor.endpoint"]
            try:
                response = make_api_call(config, url, urllib.urlencode(params))
            except urllib2.URLError:
                # @@@ add max retries
                continue
            data = json.loads(response.read())
            if data["status"] == "error":
                err("[error]\n")
                error("%s\n" % data["message"])
            if data["status"] == "success":
                if data["state"] == "finished":
                    err("[ok]\n")
                    break
                elif data["state"] == "failed":
                    err("[failed]\n")
                    err("\n%s\n" % data["reason"])
                    sys.exit(1)
                elif data["state"] == "locked":
                    err("[locked]\n")
                    err("\nYour database dump failed due to being locked. "
                        "This means there is another database dump already "
                        "in progress.\n")
                    sys.exit(1)
                else:
                    time.sleep(2)
    
    d = zlib.decompressobj(16+zlib.MAX_WBITS)
    cs = 16 * 1024
    response = urllib2.urlopen(data["result"]["public_url"])
    while True:
        chunk = response.read(cs)
        if not chunk:
            break
        out(d.decompress(chunk))


def cmd_run(args, env, config):
    
    instance_label = args.instance_label[0]
    command = args.command_[0]
    cmdargs = args.cmdargs
    params = {"cmdargs": cmdargs}
    
    if command == "createsuperuser":
        try:
            # Get a username
            while 1:
                username = raw_input("Username: ")
                if not RE_VALID_USERNAME.match(username):
                    sys.stderr.write("Error: That username is invalid. Use only letters, digits and underscores.\n")
                    username = None
                    continue
                break
            
            # Get an email
            while 1:
                email = raw_input("Email address: ")
                if not EMAIL_RE.search(email):
                    sys.stderr.write("Error: That email address is invalid.\n")
                    email = None
                else:
                    break
            
            # Get a password
            while 1:
                password = getpass.getpass()
                password2 = getpass.getpass("Password (again): ")
                if password != password2:
                    sys.stderr.write("Error: Your passwords didn't match.\n")
                    password = None
                    continue
                if password.strip() == "":
                    sys.stderr.write("Error: Blank passwords aren't allowed.\n")
                    password = None
                    continue
                break
        except KeyboardInterrupt:
            sys.stderr.write("\nOperation cancelled.\n")
            sys.exit(1)
        
        params = {
            "username": username,
            "email": email,
            "password": password,
        }
    
    out("Executing... ")
    url = "%s/instance/run/" % config["gondor.endpoint"]
    params = {
        "version": __version__,
        "site_key": config["gondor.site_key"],
        "instance_label": instance_label,
        "project_root": os.path.relpath(env["project_root"], env["repo_root"]),
        "command": command,
        "params": json.dumps(params),
        "app": json.dumps(config["app"]),
    }
    try:
        response = make_api_call(config, url, urllib.urlencode(params))
    except urllib2.HTTPError, e:
        api_error(e)
    data = json.loads(response.read())
    
    if data["status"] == "error":
        out("[error]\n")
        error("%s\n" % data["message"])
    if data["status"] == "success":
        task_id = data["task"]
        while True:
            params = {
                "version": __version__,
                "site_key": config["gondor.site_key"],
                "instance_label": instance_label,
                "task_id": task_id,
            }
            url = "%s/task/status/" % config["gondor.endpoint"]
            response = make_api_call(config, url, urllib.urlencode(params))
            data = json.loads(response.read())
            if data["status"] == "error":
                out("[error]\n")
                out("\nError: %s\n" % data["message"])
            if data["status"] == "success":
                if data["state"] == "finished":
                    out("[ok]\n")
                    d = zlib.decompressobj(16+zlib.MAX_WBITS)
                    cs = 16 * 1024
                    response = urllib2.urlopen(data["result"]["public_url"])
                    while True:
                        chunk = response.read(cs)
                        if not chunk:
                            break
                        out(d.decompress(chunk))
                    break
                elif data["state"] == "failed":
                    out("[failed]\n")
                    out("\n%s\n" % data["reason"])
                    sys.exit(1)
                elif data["state"] == "locked":
                    out("[locked]\n")
                    out("\nYour execution failed due to being locked. This means there is another execution already in progress.\n")
                    sys.exit(1)
                else:
                    time.sleep(2)


def cmd_delete(args, env, config):
    
    instance_label = args.label[0]
    
    text = "ARE YOU SURE YOU WANT TO DELETE THIS INSTANCE? [Y/N] "
    out(text)
    user_input = raw_input()
    if user_input != "Y":
        out("Exiting without deleting the instance.\n")
        sys.exit(0)
    text = "Deleting... "
    
    url = "%s/instance/delete/" % config["gondor.endpoint"]
    params = {
        "version": __version__,
        "site_key": config["gondor.site_key"],
        "instance_label": instance_label,
    }
    try:
        response = make_api_call(config, url, urllib.urlencode(params))
    except urllib2.HTTPError, e:
        api_error(e)
    data = json.loads(response.read())
    if data["status"] == "error":
        message = "error"
    elif data["status"] == "success":
        message = "ok"
    else:
        message = "unknown"
    out("\r%s[%s]   \n" % (text, message))
    if data["status"] == "error":
        error("%s\n" % data["message"])


def cmd_list(args, env, config):
    
    url = "%s/site/instances/" % config["gondor.endpoint"]
    params = {
        "version": __version__,
        "site_key": config["gondor.site_key"],
    }
    try:
        response = make_api_call(config, url, urllib.urlencode(params))
    except urllib2.HTTPError, e:
        api_error(e)
    data = json.loads(response.read())
    
    if data["status"] == "success":
        instances = sorted(data["instances"], key=lambda v: v["label"])
        if instances:
            for instance in instances:
                out("%s [%s] %s %s\n" % (
                    instance["label"],
                    instance["kind"],
                    instance["url"],
                    instance["last_deployment"]["sha"][:8]
                ))
        else:
            out("No instances found.\n")
    else:
        error("%s\n" % data["message"])


def cmd_manage(args, env, config):
    
    instance_label = args.label[0]
    operation = args.operation[0]
    opargs = args.opargs
    
    url = "%s/instance/manage/" % config["gondor.endpoint"]
    params = {
        "version": __version__,
        "site_key": config["gondor.site_key"],
        "instance_label": instance_label,
        "operation": operation,
    }
    handlers = [
        http.MultipartPostHandler,
    ]
    if not sys.stdin.isatty():
        params["stdin"] = sys.stdin
        pb = ProgressBar(0, 100, 77)
        out("Pushing stdin to Gondor... \n")
        handlers.extend([
            http.UploadProgressHandler(pb, ssl=True),
            http.UploadProgressHandler(pb, ssl=False)
        ])
    params = params.items()
    for oparg in opargs:
        params.append(("arg", oparg))
    try:
        response = make_api_call(config, url, params, extra_handlers=handlers)
    except urllib2.HTTPError, e:
        api_error(e)
    if not sys.stdin.isatty():
        out("\n")
    out("Running... ")
    data = json.loads(response.read())
    
    if data["status"] == "error":
        out("[error]\n")
        error("%s\n" % data["message"])
    if data["status"] == "success":
        if "task" in data:
            task_id = data["task"]
            while True:
                params = {
                    "version": __version__,
                    "site_key": config["gondor.site_key"],
                    "instance_label": instance_label,
                    "task_id": task_id,
                }
                url = "%s/task/status/" % config["gondor.endpoint"]
                response = make_api_call(config, url, urllib.urlencode(params))
                data = json.loads(response.read())
                if data["status"] == "error":
                    out("[error]\n")
                    out("\nError: %s\n" % data["message"])
                if data["status"] == "success":
                    if data["state"] == "finished":
                        out("[ok]\n")
                        break
                    elif data["state"] == "failed":
                        out("[failed]\n")
                        out("\n%s\n" % data["reason"])
                        sys.exit(1)
                    elif data["state"] == "locked":
                        out("[locked]\n")
                        out("\nYour task failed due to being locked. This means there is another task already in progress.\n")
                        sys.exit(1)
                    else:
                        time.sleep(2)
        else:
            out("[ok]\n")


def cmd_open(args, env, config):
    url = "%s/instance/detail/" % config["gondor.endpoint"]
    params = {
        "version": __version__,
        "site_key": config["gondor.site_key"],
        "label": args.label[0],
    }
    url += "?%s" % urllib.urlencode(params)
    try:
        response = make_api_call(config, url)
    except urllib2.HTTPError, e:
        api_error(e)
    data = json.loads(response.read())
    
    if data["status"] == "success":
        webbrowser.open(data["object"]["url"])
    else:
        error("%s\n" % data["message"])


def cmd_env(args, env, config):
    url = "%s/site/env/" % config["gondor.endpoint"]
    bits = args.bits
    params = [
        ("version", __version__),
        ("site_key", config["gondor.site_key"]),
    ]
    if args.scoped:
        params.append(("scoped", "1"))
    # default case is to get all vars on site
    if bits:
        # check if bits[0] is upper-case; if so we know it is not an instance
        # label
        if bits[0].isupper(): # get explicit var(s) on site
            params.extend([("key", k) for k in bits])
        else: # get var(s) on instance
            params.append(("label", bits[0]))
            params.extend([("key", k) for k in bits[1:]])
    url += "?%s" % urllib.urlencode(params)
    try:
        response = make_api_call(config, url)
    except urllib2.HTTPError, e:
        api_error(e)
    data = json.loads(response.read())
    if data["status"] == "success":
        if data["env"]:
            for k, v in data["env"].iteritems():
                out("%s=%s\n" % (k, v))
    else:
        error("%s\n" % data["message"])


def cmd_env_set(args, env, config):
    url = "%s/site/env/" % config["gondor.endpoint"]
    bits = args.bits
    params = [
        ("version", __version__),
        ("site_key", config["gondor.site_key"]),
    ]
    # api will reject the else case
    if bits:
        if "=" in bits[0]: # set var(s) on site
            params.extend([("variable", v) for v in bits])
        else: # set var(s) on instance
            params.append(("label", bits[0]))
            params.extend([("variable", v) for v in bits[1:]])
    try:
        response = make_api_call(config, url, urllib.urlencode(params))
    except urllib2.HTTPError, e:
        api_error(e)
    data = json.loads(response.read())
    if data["status"] == "success":
        for k, v in data["env"].iteritems():
            if v is None:
                out("removed %s\n" % k)
            else:
                out("%s=%s\n" % (k, v))
    else:
        error("%s\n" % data["message"])


def main():
    parser = argparse.ArgumentParser(prog="gondor")
    parser.add_argument("--version", action="version", version="%%(prog)s %s" % __version__)
    parser.add_argument("--verbose", "-v", action="count", default=1)
    
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
    
    # cmd: run
    parser_run = command_parsers.add_parser("run")
    parser_run.add_argument("instance_label", nargs=1)
    parser_run.add_argument("command_", nargs=1)
    parser_run.add_argument("cmdargs", nargs="*")
    
    # cmd: delete
    parser_delete = command_parsers.add_parser("delete")
    parser_delete.add_argument("label", nargs=1)
    
    # cmd: list
    parser_list = command_parsers.add_parser("list")
    
    # cmd: manage
    # example: gondor manage primary database:reset
    # example: gondor manage dev database:copy primary
    parser_manage = command_parsers.add_parser("manage")
    parser_manage.add_argument("label", nargs=1)
    parser_manage.add_argument("operation", nargs=1)
    parser_manage.add_argument("opargs", nargs="*")
    
    # cmd: open
    # example: gondor open primary
    parser_open = command_parsers.add_parser("open")
    parser_open.add_argument("label", nargs=1)
    
    # cmd: env
    # example: gondor env / gondor env primary / gondor env KEY / gondor env primary KEY
    parser_env = command_parsers.add_parser("env")
    parser_env.add_argument("--scoped", action="store_true")
    parser_env.add_argument("bits", nargs="*")
    
    # cmd: env:set
    # example: gondor env:set KEY=value / gondor env primary KEY=value
    parser_env_set = command_parsers.add_parser("env:set")
    parser_env_set.add_argument("bits", nargs="*")
    
    args = parser.parse_args()
    
    # config / env
    
    global_config = ConfigParser.RawConfigParser()
    global_config.read(os.path.expanduser("~/.gondor"))
    config = {
        "auth.username": config_value(global_config, "auth", "username"),
        "auth.password": config_value(global_config, "auth", "password"),
        "auth.key": config_value(global_config, "auth", "key"),
    }
    env = {}
    
    if args.command in ["sqldump"]:
        out = err
    else:
        out = globals()["out"]
    
    if args.command != "init":
        gondor_dirname = ".gondor"
        try:
            env["project_root"] = utils.find_nearest(os.getcwd(), gondor_dirname)
        except OSError:
            error("unable to find a .gondor directory.\n")
        
        if args.verbose > 1:
            out("Reading configuration... ")
        
        def parse_config(name):
            local_config = ConfigParser.RawConfigParser()
            local_config.read(os.path.join(env["project_root"], gondor_dirname, name))
            return local_config
        local_config = parse_config("config")
        
        if args.verbose > 1:
            out("[ok]\n")
        
        config.update({
            "auth.username": config_value(local_config, "auth", "username", config["auth.username"]),
            "auth.password": config_value(local_config, "auth", "password", config["auth.password"]),
            "auth.key": config_value(local_config, "auth", "key", config["auth.key"]),
            "gondor.site_key": config_value(local_config, "gondor", "site_key", False),
            "gondor.endpoint": config_value(local_config, "gondor", "endpoint", DEFAULT_ENDPOINT),
            "gondor.vcs": local_config.get("gondor", "vcs"),
            "app": {
                "requirements_file": config_value(local_config, "app", "requirements_file"),
                "wsgi_entry_point": config_value(local_config, "app", "wsgi_entry_point"),
                "migrations": config_value(local_config, "app", "migrations"),
                "staticfiles": config_value(local_config, "app", "staticfiles"),
                "compressor": config_value(local_config, "app", "compressor"),
                "site_media_url": config_value(local_config, "app", "site_media_url"),
                "settings_module": config_value(local_config, "app", "settings_module"),
                "managepy": config_value(local_config, "app", "managepy"),
                "local_settings": config_value(local_config, "app", "local_settings"),
            }
        })
        
        if not config["gondor.site_key"]:
            if args.verbose > 1:
                out("Loading separate site_key... ")
            try:
                site_key_config = parse_config("site_key")
                config["gondor.site_key"] = site_key_config.get("gondor", "site_key")
            except ConfigParser.NoSectionError:
                if args.verbose > 1:
                    out("[failed]\n")
                error("Unable to read gondor.site_key from .gondor/config or .gondor/site_key\n");
            if args.verbose > 1:
                out("[ok]\n")
        
        try:
            vcs_dir = {"git": ".git", "hg": ".hg"}[config["gondor.vcs"]]
        except KeyError:
            error("'%s' is not a valid version control system for Gondor\n" % config["gondor.vcs"])
        try:
            env["repo_root"] = utils.find_nearest(os.getcwd(), vcs_dir)
        except OSError:
            error("unable to find a %s directory.\n" % vcs_dir)
    
    if (config["auth.username"] is None and (config["auth.password"] is None or config["auth.key"] is None)):
        message = "you must set your credentials in %s" % os.path.expanduser("~/.gondor")
        if "project_root" in env:
            message += " or %s" % os.path.join(env["project_root"], ".gondor", "config")
        message += "\n"
        error(message)
    
    {
        "init": cmd_init,
        "create": cmd_create,
        "deploy": cmd_deploy,
        "sqldump": cmd_sqldump,
        "run": cmd_run,
        "delete": cmd_delete,
        "list": cmd_list,
        "manage": cmd_manage,
        "open": cmd_open,
        "env": cmd_env,
        "env:set": cmd_env_set,
    }[args.command](args, env, config)
