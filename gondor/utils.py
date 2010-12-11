import subprocess


def check_output(cmd):
    p = subprocess.Popen([cmd], stdout=subprocess.PIPE, shell=True)
    return p.communicate()[0]