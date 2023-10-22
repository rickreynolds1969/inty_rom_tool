import subprocess


def exc(cmd):
    rslt = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
    return rslt

    # try:
    #     rslt = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
    #     return rslt
    # except subprocess.CalledProcessError as procerr:
    #     raise
    #     print "error code", procerr.returncode, procerr.output
    # except Exception as errmsg:
    #     raise
    #     print "Exception in execute_shell_command: %s" % errmsg
