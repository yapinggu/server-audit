#! /usr/bin/python

# Copyright 2013 Cisco Systems, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import platform
import getpass
import argparse
import yaml
from ImcSdk import *
#http://www.cisco.com/c/en/us/td/docs/unified_computing/ucs/release/notes/Release_Notes_for_Cisco_C-Series_SW_2_0_3.html#pgfId-758902
#table 6 and table 7
#http://www.cisco.com/c/en/us/td/docs/unified_computing/ucs/release/firmware_files/2_0_x/b_UCS_C-Series_Firmware_Files_2_0_x/b_UCS_C-Series_Firmware_Files_2_0_x_chapter_01.html#id_10134__section_A593E8C4254D4FE9BCE8FDFD9DDBAD54
handle_list = []

def get_password():
    if platform.system() == "Linux":
        return getpass.unix_getpass()
    elif platform.system() == "Windows" or platform.system() == "Microsoft":
        return getpass.win_getpass()
    else:
        return getpass.getpass()

def do_login(ip,user,pwd):
    print "------------------------------"
    print "Connecting to IMC Server <%s>" %(ip)
    handle = ImcHandle()
    if handle.login(ip,user,pwd):
        #print "login successful: <%s>" %(handle.name)
        handle_list.append(handle)
        return handle

def do_logout():
    for handle in handle_list:
        handle_name = handle.name
        if handle.logout():
            print "logout successful: <%s>" %(handle_name)

def getServerModel(handle):
    devices = handle.get_imc_managedobject(None, params={'Dn': "sys/rack-unit-1"})
    if len(devices)==0:
        print "No such server"
        # Close the session
        do_logout()
        exit(1)
    serverModel = (devices[0].__dict__)['Model']
    #print "Server Model: %s"%serverModel
    return serverModel

def audit_fw_version(version, component, expected_fw_version_list):
    fw_match = False
    # if expected firmare version list is empty, match is true
    if len(expected_fw_version_list) == 0:
        fw_match = True
        return fw_match
    for expected_fw_version in expected_fw_version_list:
        if (expected_fw_version in version):
            print "OK: %s version %s matched expected version %s"%(component, version, expected_fw_version) 
            fw_match = True
            break
    if not fw_match:
        print "Error: %s version %s didn't match expected version %s"%(component, version, expected_fw_version_list)
    return fw_match

def get_fw_version_for_DN(handle, moDn):
    fwRunning_mo =  handle.get_imc_managedobject(params={'Dn': moDn})
    fw_version = ""
    if fwRunning_mo:
        fw_version = fwRunning_mo[0].get_attr("Version")
    else:
        print "Error in get_fw_version_for_DN: fwRunning_mo not found for dn %s"%(moDn)
    return fw_version

def get_fw_version_by_class_id(handle, class_id, fwdn_postfix, expected_fw_version_list, current_fw_dict):
    fw_match = True
    mo_list = get_molist_by_class_id(handle,class_id)
    if (mo_list):
        for mo in mo_list:
            #print mo
            mo_dn=mo.get_attr("Dn")
            mo_fw_dn = mo_dn + fwdn_postfix
            #print "mo dn: %s, mo fw dn: %s"%(mo_dn, mo_fw_dn)
            fw_version = ""
            fw_version=get_fw_version_for_DN(handle, mo_fw_dn)
            current_fw_dict[mo_fw_dn] = fw_version
            #print "%s firmware version: %s"%(mo_fw_dn, fw_version)
            mo_fw_match = audit_fw_version(fw_version, class_id, expected_fw_version_list)
            if not mo_fw_match:
                fw_match = False
                print "Error: firmware version %s for %s is different from expected %s!"%(fw_version, mo_fw_dn, expected_fw_version_list)

    return fw_match

def get_molist_by_class_id(handle,class_id,in_hierarchical=False):
    return handle.get_imc_managedobject(None,
                                      class_id,
                                      params=None,
                                      in_hierarchical=in_hierarchical)

def check_pcie_fw(pcieMo, expected_fw_info):
    pcie_model = pcieMo.Model
    expected_fw_version_list= []

    # go through each PCIE expected firmware info
    for pcieName, expectedPcie in expected_fw_info.iteritems():
        model = ""
        fw_version_list = []
        for attrName, attrValue in expectedPcie.iteritems():
            if "Model" == attrName:
                model = attrValue
            elif "Version" == attrName:
                for fw_version in attrValue:
                    fw_version_list.append(fw_version)

        if model == pcie_model:
            expected_fw_version_list = fw_version_list
            break
    # if component don't have expected fw version defined like intel card, just return True
    return audit_fw_version(pcieMo.Version, pcie_model, expected_fw_version_list)

def main(args):
    #load yaml file
    expected_fw_info = yaml.load(args.expected_fw_info)
    overall_fw_match_expected_flag = True

    #Connect to IMC
    handle=do_login(args.ip,args.username,args.password)

    current_fw_dict = {}
    svrModel = getServerModel(handle)
    for type, svr_fw_info in expected_fw_info.iteritems():
      if (type == "UCSC_expected_fw_version"):
        for svr_type, components in svr_fw_info.iteritems():
          # based on server model, use fw info that match that server model
          if (svr_type in svrModel):
            print "server model: %s matching %s"%(svrModel, svr_type)
            for component, fw_info in components.iteritems():
              compName = component
              comp_fw_match_expected_flag = True

              if(compName == "pciEquipSlot"):
                pcie_fw_match_expected_flag = True
                mo_list = get_molist_by_class_id(handle,compName)
                for mo in mo_list:
                    #print mo
                    pcie_fw_match_expected_flag = check_pcie_fw(mo, fw_info)
                    if not pcie_fw_match_expected_flag:
                        comp_fw_match_expected_flag = False
              else:
                compFwDn = ""
                class_id = ""
                fw_postfix = ""
                expected_fw_version_list=[]
                for attrName, attrValue in fw_info.iteritems():
                    if "DN" == attrName:
                        compFwDn = attrValue
                    if "Version" in attrName:
                        for fw_version in attrValue:
                            #print "expected_fw_version: %s for %s"%(fw_version, component)
                            expected_fw_version_list.append(fw_version)
                    if "class_id" in attrName:
                        class_id = attrValue
                    if "fw_postfix" in attrName:
                        fw_postfix = attrValue

                if len(compFwDn) > 0 :
                    #print "calling get_fw_version_for_DN"
                    comp_running_version = get_fw_version_for_DN(handle, compFwDn)
                    comp_fw_match_expected_flag = audit_fw_version(comp_running_version, compName, expected_fw_version_list)
                    current_fw_dict[compName] = comp_running_version
                elif len(class_id) > 0 :
                    #print "calling get_fw_version_by_class_id!"
                    comp_fw_match_expected_flag = get_fw_version_by_class_id(handle, compName, fw_postfix, expected_fw_version_list, current_fw_dict)

              # any component firmware version not as expected, will raise the flag to False
              if not comp_fw_match_expected_flag:
                  overall_fw_match_expected_flag = False

    if overall_fw_match_expected_flag:
        print "All Good!"
    else:
        print "Overall Error: Major components have unexpected firmware versions"

    do_logout()

if __name__ == "__main__":
        parser = argparse.ArgumentParser(description="Audit UCS standalone server firmware version")

        parser.add_argument('-f', '--expected_fw_info', dest='expected_fw_info',
                            type=argparse.FileType('r'), required=True,
                            help='[Mandatory]YAML file for expected firmware version info')
        parser.add_argument('-i', '--ip',dest="ip",
                            help="[Mandatory] IMC IP Address")
        parser.add_argument('-u', '--username', dest='username', required=True,
                            help='[Mandatory]Account Username for IMC login')
        parser.add_argument('-p', '--password', dest='password', required=True,
                            help='[Mandatory]Password for the admin user')

        args = parser.parse_args()
        main(args)
