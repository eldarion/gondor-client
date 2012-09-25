import argparse
import ConfigParser
import gzip
import itertools
import os
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib
import urllib2
import webbrowser
import zlib

try:
    import simplejson as json
except ImportError:
    import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "yaml-3.10.zip")))
import yaml

from gondor import __version__
from gondor import http, utils
from gondor.api import make_api_call
from gondor.prettytable import PrettyTable
from gondor.progressbar import ProgressBar
from gondor.run import unix_run_poll, win32_run_poll
from gondor.utils import out, err, error, warn, api_error


DEFAULT_ENDPOINT = "https://api.gondor.io"


def config_value(config, section, key, default=None):
    try:
        return config.get(section, key)
    except (ConfigParser.NoOptionError, ConfigParser.NoSectionError):
        return default


def load_config(args, kind):
    config_file = {
        "global": os.path.join(os.path.expanduser("~"), ".gondor"),
        "local": os.path.abspath(os.path.join(os.curdir, "gondor.yml")),
    }[kind]
    try:
        return yaml.load(open(config_file, "rb"))
    except IOError:
        error("unable to find configuration file (looked for %s)\n" % config_file)
    except yaml.parser.ParserError:
        if kind == "global":
            c = ConfigParser.RawConfigParser()
            try:
                c.read(config_file)
            except Exception:
                # ignore any exceptions while reading config
                pass
            else:
                if args.verbose > 1:
                    warn("upgrade %s to YAML\n" % config_file)
                return {
                    "auth": {
                        "username": config_value(c, "auth", "username"),
                        "key": config_value(c, "auth", "key"),
                    }
                }
        error("unable to parse %s\n" % config_file)


def cmd_init(args, env, config):
    config_file = "gondor.yml"
    ctx = dict(config_file=config_file)
    if args.upgrade:
        gondor_dir = utils.find_nearest(os.getcwd(), ".gondor")
        legacy_config = ConfigParser.RawConfigParser()
        legacy_config.read(os.path.abspath(os.path.join(gondor_dir, ".gondor", "config")))
        ctx.update({
            "site_key": config_value(legacy_config, "gondor", "site_key"),
            "vcs": config_value(legacy_config, "gondor", "vcs"),
            "requirements_file": config_value(legacy_config, "app", "requirements_file"),
            "wsgi_entry_point": config_value(legacy_config, "app", "wsgi_entry_point"),
            "framework": "django",
            "gunicorn_worker_class": "eventlet",
        })
        on_deploy, static_urls = [], []
        migrations = config_value(legacy_config, "app", "migrations")
        if migrations:
            migrations = migrations.strip().lower()
            if migrations == "none":
                on_deploy.append("    - manage.py syncdb --noinput")
            if migrations == "nashvegas":
                on_deploy.append("    - manage.py upgradedb --execute")
            if migrations == "south":
                on_deploy.append("    - manage.py syncdb --noinput")
                on_deploy.append("    - manage.py migrate --noinput")
        staticfiles = config_value(legacy_config, "app", "staticfiles")
        if staticfiles:
            staticfiles = staticfiles.strip().lower()
            if staticfiles == "on":
                on_deploy.append("    - manage.py collectstatic --noinput")
        compressor = config_value(legacy_config, "app", "compressor")
        if compressor:
            compressor = compressor.strip().lower()
            if compressor == "on":
                on_deploy.append("    - manage.py compress")
        site_media_url = config_value(legacy_config, "app", "site_media_url")
        managepy = config_value(legacy_config, "app", "managepy")
        if not managepy:
            managepy = "manage.py"
        if site_media_url:
            static_urls.extend(["    - %s:" % site_media_url, "        root: site_media/"])
        extra_config_file_data = """
django:
    # The location of your manage.py. Gondor uses this as an entry point for
    # management commands. This path is relative to your project root (the
    # directory %(config_file)s lives in.)
    managepy: %(managepy)s
""" % {
    "managepy": managepy,
    "config_file": config_file,
}
    else:
        site_key = args.site_key
        if len(site_key) < 11:
            error("The site key given is too short.\n")
        ctx["wsgi_entry_point"] = "wsgi:application"
        ctx["requirements_file"] = "requirements.txt"
        on_deploy = []
        static_urls = ["    - /site_media:", "        root: site_media/"]
        try:
            utils.find_nearest(os.getcwd(), ".git")
        except OSError:
            try:
                utils.find_nearest(os.getcwd(), ".hg")
            except OSError:
                error("unable to find a supported version control directory. Looked for .git and .hg.\n")
            else:
                vcs = "hg"
        else:
            vcs = "git"
        extra_config_file_data = ""
        ctx.update({
            "site_key": site_key,
            "vcs": vcs,
            "framework": "wsgi",
            "requirements_file": "requirements.txt",
            "wsgi_entry_point": "wsgi:application",
            "gunicorn_worker_class": "sync",
        })
    if not on_deploy:
        ctx["on_deploy"] = "# on_deploy:\n#     - manage.py syncdb --noinput\n#     - manage.py collectstatic --noinput"
    else:
        ctx["on_deploy"] = "\n".join(["on_deploy:"] + on_deploy)
    ctx["static_urls"] = "\n".join(["static_urls:"] + static_urls)
    if not os.path.exists(config_file):
        config_file_data = """# The key associated to your site.
key: %(site_key)s

# Version control system used locally for your project.
vcs: %(vcs)s

# Framework to use on Gondor.
framework: %(framework)s

# This path is relative to your project root (the directory %(config_file)s lives in.)
requirements_file: %(requirements_file)s

# Commands to be executed during deployment. These can handle migrations or
# moving static files into place. Accepts same parameters as gondor run.
%(on_deploy)s

# URLs which should be served by Gondor mapping to a filesystem location
# relative to your writable storage area.
%(static_urls)s

wsgi:
    # The WSGI entry point of your application in two parts separated by a
    # colon. Example:
    #
    #     wsgi:application
    #
    # wsgi = the Python module which should be importable
    # application = the callable in the Python module
    entry_point: %(wsgi_entry_point)s
    
    # Options for gunicorn which runs your WSGI project.
    gunicorn:
        # The worker class used to run gunicorn (possible values include:
        # sync, eventlet and gevent)
        worker_class: %(gunicorn_worker_class)s
""" % ctx
        out("Writing configuration (%s)... " % config_file)
        with open(config_file, "wb") as cf:
            cf.write(config_file_data + extra_config_file_data)
        out("[ok]\n")
        if args.upgrade:
            out("\nYour configuration file has been upgraded. New configuration is located\n")
            out("in %s. Make sure you check this file before continuing then add and\n" % config_file)
            out("commit it to your VCS.\n")
        else:
            out("\nYou are now ready to deploy your project to Gondor. You might want to first\n")
            out("check %s (in this directory) for correct values for your\n" % config_file)
            out("application. Once you are ready, run:\n\n")
            out("    gondor deploy primary %s\n" % {"git": "master", "hg": "default"}[vcs])
    else:
        out("Detected existing %s. Not overriding.\n" % config_file)


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
                "run_on_deploy": {True: "true", False: "false"}[not args.no_on_deploy],
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
                out("\n")
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
    command = args.command_
    
    if args.detached:
        err("Spawning... ")
    else:
        err("Attaching... ")
    url = "%s/instance/run/" % config["gondor.endpoint"]
    params = {
        "version": __version__,
        "site_key": config["gondor.site_key"],
        "instance_label": instance_label,
        "project_root": os.path.relpath(env["project_root"], env["repo_root"]),
        "detached": {True: "true", False: "false"}[args.detached],
        "command": " ".join(command),
        "app": json.dumps(config["app"]),
    }
    if sys.platform == "win32":
        params["term"] = "win32"
    if "TERM" in os.environ:
        try:
            params.update({
                "tc": utils.check_output(["tput", "cols"]).strip(),
                "tl": utils.check_output(["tput", "lines"]).strip(),
            })
        except (OSError, subprocess.CalledProcessError):
            # if the above fails then no big deal; we just can't set correct
            # terminal info so it will default some common values
            pass
    try:
        response = make_api_call(config, url, urllib.urlencode(params))
    except urllib2.HTTPError, e:
        err("[failed]\n")
        api_error(e)
    data = json.loads(response.read())
    endpoint = None if args.detached else tuple(data["endpoint"])
    if data["status"] == "error":
        err("[error]\n")
        error("%s\n" % data["message"])
    if data["status"] == "success":
        task_id = data["task"]
        tc, tl = data["tc"], data["tl"]
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
                err("[error]\n")
                error("%s\n" % data["message"])
            if data["status"] == "success":
                if data["state"] == "finished":
                    if args.detached:
                        err("[ok]\n")
                    # task finished; move on
                    break
                elif data["state"] == "failed":
                    err("[failed]\n")
                    error("%s\n" % data["reason"])
                elif data["state"] == "locked":
                    err("[locked]\n")
                    err("\nYour execution failed due to being locked. This means there is another execution already in progress.\n")
                    sys.exit(1)
                else:
                    time.sleep(2)
        if args.detached:
            err("Check your logs for output.\n")
        else:
            # connect to process
            for x in xrange(5):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                ssl_kwargs = {
                    "ca_certs": os.path.join(os.path.abspath(os.path.dirname(__file__)), "ssl", "run.gondor.io.crt"),
                    "cert_reqs": ssl.CERT_REQUIRED,
                    "ssl_version": ssl.PROTOCOL_SSLv3
                }
                sock = ssl.wrap_socket(sock, **ssl_kwargs)
                try:
                    sock.connect(endpoint)
                except IOError, e:
                    time.sleep(0.5)
                    continue
                else:
                    err("[ok]\n")
                    if args.verbose > 1:
                        err("Terminal set to %sx%s\n" % (tc, tl))
                    break
            else:
                err("[failed]\n")
                error("unable to attach to process (reason: %s)\n" % e)
            if sys.platform == "win32":
                win32_run_poll(sock)
            else:
                unix_run_poll(sock)


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
            table = PrettyTable(["label", "kind", "URL", "deployed", "reqs/sec", "avg time/req"])
            table.align = "l"
            for instance in instances:
                table.add_row([
                    instance["label"],
                    instance["kind"],
                    instance["url"],
                    instance["last_deployment"]["sha"][:8],
                    instance["avg_requests_per_second"],
                    instance["avg_request_duration"],
                ])
            print table
        else:
            out("No instances found.\n")
    else:
        error("%s\n" % data["message"])


def cmd_manage(args, env, config):
    
    instance_label = args.label[0]
    operation = args.operation[0]
    opargs = args.opargs
    
    if operation == "database:load" and not args.yes:
        out("This command will destroy all data in the database for %s\n" % instance_label)
        answer = raw_input("Are you sure you want to continue? [y/n]: ")
        if answer != "y":
            sys.exit(1)
    
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
    if operation in ["database:load"]:
        if opargs:
            filename = os.path.abspath(os.path.expanduser(opargs[0]))
            try:
                fp = open(filename, "rb")
            except IOError:
                error("unable to open %s\n" % filename)
            out("Compressing file... ")
            fd, tmp = tempfile.mkstemp()
            fpc = gzip.open(tmp, "wb")
            try: 
                while True:
                    chunk = fp.read(8192)
                    if not chunk:
                        break
                    fpc.write(chunk)
            finally:
                fpc.close()
            out("[ok]\n")
            params["stdin"] = open(tmp, "rb")
            pb = ProgressBar(0, 100, 77)
            out("Pushing file to Gondor... \n")
            handlers.extend([
                http.UploadProgressHandler(pb, ssl=True),
                http.UploadProgressHandler(pb, ssl=False)
            ])
        else:
            error("%s takes one argument.\n" % operation)
    params = params.items()
    for oparg in opargs:
        params.append(("arg", oparg))
    try:
        response = make_api_call(config, url, params, extra_handlers=handlers)
    except urllib2.HTTPError, e:
        api_error(e)
    out("\nRunning... ")
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


def cmd_dashboard(args, env, config):
    params = {
        "version": __version__,
        "site_key": config["gondor.site_key"],
    }
    if args.label:
        url = "%s/instance/detail/" % config["gondor.endpoint"]
        params["label"] = args.label
    else:
        url = "%s/site/detail/" % config["gondor.endpoint"]
    url += "?%s" % urllib.urlencode(params)
    try:
        response = make_api_call(config, url)
    except urllib2.HTTPError, e:
        api_error(e)
    data = json.loads(response.read())
    
    if data["status"] == "success":
        webbrowser.open(data["object"]["dashboard_url"])
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
    parser_init.add_argument("--upgrade", action="store_true")
    parser_init.add_argument("site_key", nargs="?")
    
    # cmd: create
    parser_create = command_parsers.add_parser("create")
    parser_create.add_argument("--kind")
    parser_create.add_argument("label", nargs=1)
    
    # cmd: deploy
    parser_deploy = command_parsers.add_parser("deploy")
    parser_deploy.add_argument("--no-on-deploy", action="store_true")
    parser_deploy.add_argument("label", nargs=1)
    parser_deploy.add_argument("commit", nargs=1)
    
    # cmd: sqldump
    parser_sqldump = command_parsers.add_parser("sqldump")
    parser_sqldump.add_argument("label", nargs=1)
    
    # cmd: run
    parser_run = command_parsers.add_parser("run")
    parser_run.add_argument("--detached",
        action="store_true",
        help="run process in detached (output is sent to logs)"
    )
    parser_run.add_argument("instance_label", nargs=1)
    parser_run.add_argument("command_", nargs=argparse.REMAINDER)
    
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
    parser_manage.add_argument("--yes",
        action="store_true",
        help="automatically answer yes to prompts"
    )
    parser_manage.add_argument("opargs", nargs="*")
    
    # cmd: open
    # example: gondor open primary
    parser_open = command_parsers.add_parser("open")
    parser_open.add_argument("label", nargs=1)
    
    # cmd: dashboard
    # example: gondor dashboard primary
    parser_dashboard = command_parsers.add_parser("dashboard")
    parser_dashboard.add_argument("label", nargs="?")
    
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
    
    global_config = load_config(args, "global")
    config = {
        "auth.username": global_config.get("auth", {}).get("username"),
        "auth.key": global_config.get("auth", {}).get("key"),
    }
    env = {}
    
    if args.command in ["sqldump"]:
        out = err
    else:
        out = globals()["out"]
    
    if args.command != "init":
        config_file = "gondor.yml"
        try:
            env["project_root"] = utils.find_nearest(os.getcwd(), config_file)
        except OSError:
            error("unable to find %s configuration file.\n" % config_file)
        
        if args.verbose > 1:
            out("Reading configuration... ")
        
        local_config = load_config(args, "local")
        
        if args.verbose > 1:
            out("[ok]\n")
        
        config.update({
            "auth.username": local_config.get("auth", {}).get("username", config["auth.username"]),
            "auth.key": local_config.get("auth", {}).get("key", config["auth.key"]),
            "gondor.site_key": local_config.get("key"),
            "gondor.endpoint": local_config.get("endpoint", DEFAULT_ENDPOINT),
            "gondor.vcs": local_config.get("vcs"),
            "app": {
                "requirements_file": local_config.get("requirements_file"),
                "framework": local_config.get("framework"),
                "on_deploy": local_config.get("on_deploy", []),
                "static_urls": list(itertools.chain(*[
                    [(u, c) for u, c in su.iteritems()]
                    for su in local_config.get("static_urls", [])
                ])),
                "wsgi_entry_point": local_config.get("wsgi", {}).get("entry_point"),
                "gunicorn_worker_class": local_config.get("wsgi", {}).get("gunicorn", {}).get("worker_class"),
                "settings_module": local_config.get("django", {}).get("settings_module"),
                "managepy": local_config.get("django", {}).get("managepy"),
                "local_settings": local_config.get("django", {}).get("local_settings"),
                "env": local_config.get("env", {}),
            }
        })
        
        # allow some values to be overriden from os.environ
        config["auth.username"] = os.environ.get("GONDOR_AUTH_USERNAME", config["auth.username"])
        config["auth.key"] = os.environ.get("GONDOR_AUTH_KEY", config["auth.key"])
        config["gondor.site_key"] = os.environ.get("GONDOR_SITE_KEY", config["gondor.site_key"])
        
        try:
            vcs_dir = {"git": ".git", "hg": ".hg"}[config["gondor.vcs"]]
        except KeyError:
            error("'%s' is not a valid version control system for Gondor\n" % config["gondor.vcs"])
        try:
            env["repo_root"] = utils.find_nearest(os.getcwd(), vcs_dir)
        except OSError:
            error("unable to find a %s directory.\n" % vcs_dir)
        
        if config["auth.username"] is None or config["auth.key"] is None:
            error(
                "you must provide a username and API key in %s or set it in "
                "the environment.\n" % os.path.expanduser("~/.gondor")
            )
        
        if config["gondor.site_key"] is None:
            error("no site key found in configuration or environment.\n")
    
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
        "dashboard": cmd_dashboard,
        "env": cmd_env,
        "env:set": cmd_env_set,
    }[args.command](args, env, config)
    return 0
