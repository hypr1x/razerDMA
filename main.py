import sys
from ctypes import *
from ctypes.wintypes import *
import zmq
import colorama
from colorama import Fore
colorama.init(autoreset=True)

context = zmq.Context()
socket = context.socket(zmq.PULL)
try:
    socket.bind("tcp://*:12345")
except zmq.ZMQError as e:
    print(f"{Fore.RED}[-] ZMQ Error during binding: {e}")
    sys.exit(1)

ntdll = windll.ntdll
kernel32 = windll.kernel32

NTSTATUS = c_long
STATUS_SUCCESS = NTSTATUS(0x00000000).value
STATUS_UNSUCCESSFUL = NTSTATUS(0xC0000001).value
STATUS_BUFFER_TOO_SMALL = NTSTATUS(0xC0000023).value
PVOID = c_void_p
PWSTR = c_wchar_p
DIRECTORY_QUERY = 0x0001
OBJ_CASE_INSENSITIVE = 0x00000040
INVALID_HANDLE_VALUE = -1
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3


class UNICODE_STRING(Structure):
    _fields_ = [("Length", USHORT), ("MaximumLength", USHORT), ("Buffer", PWSTR)]


class OBJECT_ATTRIBUTES(Structure):
    _fields_ = [
        ("Length", ULONG),
        ("RootDirectory", HANDLE),
        ("ObjectName", POINTER(UNICODE_STRING)),
        ("Attributes", ULONG),
        ("SecurityDescriptor", PVOID),
        ("SecurityQualityOfService", PVOID),
    ]


class OBJECT_DIRECTORY_INFORMATION(Structure):
    _fields_ = [("Name", UNICODE_STRING), ("TypeName", UNICODE_STRING)]


def InitializeObjectAttributes(
    InitializedAttributes, ObjectName, Attributes, RootDirectory, SecurityDescriptor
):
    memset(addressof(InitializedAttributes), 0, sizeof(InitializedAttributes))
    InitializedAttributes.Length = sizeof(InitializedAttributes)
    InitializedAttributes.ObjectName = ObjectName
    InitializedAttributes.Attributes = Attributes
    InitializedAttributes.RootDirectory = RootDirectory
    InitializedAttributes.SecurityDescriptor = SecurityDescriptor
    InitializedAttributes.SecurityQualityOfService = None


def RtlInitUnicodeString(DestinationString, Src):
    memset(addressof(DestinationString), 0, sizeof(DestinationString))
    DestinationString.Buffer = cast(Src, PWSTR)
    DestinationString.Length = sizeof(Src) - 2
    DestinationString.MaximumLength = DestinationString.Length
    return STATUS_SUCCESS


def open_directory(root_handle, dir, desired_access):
    status = STATUS_UNSUCCESSFUL
    dir_handle = c_void_p()
    us_dir = UNICODE_STRING()
    p_us_dir = None
    if dir:
        w_dir = create_unicode_buffer(dir)
        us_dir = UNICODE_STRING()
        status = RtlInitUnicodeString(us_dir, w_dir)
        p_us_dir = pointer(us_dir)
        if status != STATUS_SUCCESS:
            print("RtlInitUnicodeString failed.")
            sys.exit(0)
    obj_attr = OBJECT_ATTRIBUTES()
    InitializeObjectAttributes(
        obj_attr, p_us_dir, OBJ_CASE_INSENSITIVE, root_handle, None
    )
    status = ntdll.NtOpenDirectoryObject(
        byref(dir_handle), desired_access, byref(obj_attr)
    )
    if status != STATUS_SUCCESS:
        print("NtOpenDirectoryObject failed.")
        sys.exit(0)
    return dir_handle


def find_sym_link(dir, name):
    dir_handle = open_directory(None, "\\GLOBAL??", DIRECTORY_QUERY)
    if not dir_handle:
        sys.exit(0)
    status = STATUS_UNSUCCESSFUL
    query_context = ULONG(0)
    length = ULONG()
    objinf = OBJECT_DIRECTORY_INFORMATION()
    found = False
    out = None
    while True:
        status = ntdll.NtQueryDirectoryObject(
            dir_handle, 0, 0, True, False, byref(query_context), byref(length)
        )
        if status != STATUS_BUFFER_TOO_SMALL:
            print("NtQueryDirectoryObject failed.")
            sys.exit(0)
        p_objinf = pointer(objinf)
        status = ntdll.NtQueryDirectoryObject(
            dir_handle,
            p_objinf,
            length,
            True,
            False,
            byref(query_context),
            byref(length),
        )
        if status != STATUS_SUCCESS:
            print("NtQueryDirectoryObject failed.")
            sys.exit(0)
        _name = objinf.Name.Buffer
        if name in _name:
            found = True
            out = _name
            break
    ntdll.NtClose(dir_handle)
    return found, out


def enum(**enums):
    return type("Enum", (), enums)


MOUSE_CLICK = enum(
    LEFT_DOWN=1,
    LEFT_UP=2,
    RIGHT_DOWN=4,
    RIGHT_UP=8,
    SCROLL_CLICK_DOWN=16,
    SCROLL_CLICK_UP=32,
    BACK_DOWN=64,
    BACK_UP=128,
    FOWARD_DOWN=256,
    FOWARD_UP=512,
    SCROLL_DOWN=4287104000,
    SCROLL_UP=7865344,
)

KEYBOARD_INPUT_TYPE = enum(KEYBOARD_DOWN=0, KEYBOARD_UP=1)


class RZCONTROL_IOCTL_STRUCT(Structure):
    _fields_ = [
        ("unk0", c_int32),
        ("unk1", c_int32),
        ("max_val_or_scan_code", c_int32),
        ("click_mask", c_int32),
        ("unk3", c_int32),
        ("x", c_int32),
        ("y", c_int32),
        ("unk4", c_int32),
    ]


IOCTL_MOUSE = 0x88883020
MAX_VAL = 65536
RZCONTROL_MOUSE = 2
RZCONTROL_KEYBOARD = 1


class RZCONTROL:

    hDevice = INVALID_HANDLE_VALUE

    def __init__(self):
        pass

    def init(self):
        if RZCONTROL.hDevice != INVALID_HANDLE_VALUE:
            kernel32.CloseHandle(RZCONTROL.hDevice)
        found, name = find_sym_link("\\GLOBAL??", "RZCONTROL")
        if not found:
            return False
        sym_link = "\\\\?\\" + name
        RZCONTROL.hDevice = kernel32.CreateFileW(
            sym_link, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, 0, OPEN_EXISTING, 0, 0
        )
        return RZCONTROL.hDevice != INVALID_HANDLE_VALUE

    def impl_mouse_ioctl(self, ioctl):
        if ioctl:
            p_ioctl = pointer(ioctl)
            junk = c_ulong()
            bResult = kernel32.DeviceIoControl(
                RZCONTROL.hDevice,
                IOCTL_MOUSE,
                p_ioctl,
                sizeof(RZCONTROL_IOCTL_STRUCT),
                0,
                0,
                byref(junk),
                0,
            )
            if not bResult:
                self.init()

    def mouse_move(self, x, y, from_start_point):
        """if going from point, x and y will be the offset from current mouse position
               otherwise it will be a number in range of 1 to 65536, where 1, 1 is top left of screen
               if using multiple monitors the input values remain the same, but outcome different, i just don't recommend bothering with this bs
               note: x and/or y can not be 0 unless going from start point

        Args:
            x (int)
            y (int)
            from_start_point (bool)
        """
        max_val = 0
        if not from_start_point:
            max_val = MAX_VAL
            if x < 1:
                x = 1
            if x > max_val:
                x = max_val
            if y < 1:
                y = 1
            if y > max_val:
                y = max_val
        mm = RZCONTROL_IOCTL_STRUCT(0, RZCONTROL_MOUSE, max_val, 0, 0, x, y, 0)
        self.impl_mouse_ioctl(mm)

    def mouse_click(self, click_mask):
        """
        Args:
            click_mask (MOUSE_CLICK):
        """
        mm = RZCONTROL_IOCTL_STRUCT(
            0,
            RZCONTROL_MOUSE,
            0,
            click_mask,
            0,
            0,
            0,
            0,
        )
        self.impl_mouse_ioctl(mm)

    def keyboard_input(self, scan_code, up_down):
        """
        Args:
            scan_code (short): https://www.millisecond.com/support/docs/current/html/language/scancodes.htm
            up_down (KEYBOARD_INPUT_TYPE): _description_
        """
        mm = RZCONTROL_IOCTL_STRUCT(
            0,
            RZCONTROL_KEYBOARD,
            (int(scan_code) << 16),
            up_down,
            0,
            0,
            0,
            0,
        )
        self.impl_mouse_ioctl(mm)

from pystyle import Box, Center, Colorate, Colors, System, Write
BANNER = """








██╗  ██╗██╗   ██╗██████╗ ███████╗██████╗     ██████╗ ██████╗ ██╗██╗   ██╗ █████╗ ████████╗███████╗
██║  ██║╚██╗ ██╔╝██╔══██╗██╔════╝██╔══██╗    ██╔══██╗██╔══██╗██║██║   ██║██╔══██╗╚══██╔══╝██╔════╝
███████║ ╚████╔╝ ██████╔╝█████╗  ██████╔╝    ██████╔╝██████╔╝██║██║   ██║███████║   ██║   █████╗  
██╔══██║  ╚██╔╝  ██╔═══╝ ██╔══╝  ██╔══██╗    ██╔═══╝ ██╔══██╗██║╚██╗ ██╔╝██╔══██║   ██║   ██╔══╝  
██║  ██║   ██║   ██║     ███████╗██║  ██║    ██║     ██║  ██║██║ ╚████╔╝ ██║  ██║   ██║   ███████╗
╚═╝  ╚═╝   ╚═╝   ╚═╝     ╚══════╝╚═╝  ╚═╝    ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═══╝  ╚═╝  ╚═╝   ╚═╝   ╚══════╝
                                        
"""
def main():

    rzctl = RZCONTROL()

    if not rzctl.init(): print("Failed to initialize rzctl")
    print(Colorate.Horizontal(Colors.blue_to_purple, Center.XCenter(BANNER), 1))
    print(Colorate.Horizontal(Colors.blue_to_purple, Center.XCenter("-======================================$$======================================-"), 1))
    print(Colorate.Horizontal(Colors.blue_to_purple, Center.XCenter(""), 1))
    print(Colorate.Horizontal(Colors.blue_to_purple, Center.XCenter("Github.com/hypr1x"), 1))
    
    while True:
        try:
            message = socket.recv_string()
        except:
            pass
        if message == "click":
            rzctl.mouse_click(MOUSE_CLICK.LEFT_DOWN)
            # time.sleep(1 / 1000)
            rzctl.mouse_click(MOUSE_CLICK.LEFT_UP)
        else:
            x, y = map(int, message.split(','))
            rzctl.mouse_move(x, y, True)
        # time.sleep(
        #     1 / 1000
        # )  # Sleep is needed to avoid razer service overflowing, which delays all your inputs



if __name__ == "__main__":
    main()
