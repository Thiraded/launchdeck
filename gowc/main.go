// gowc — fast Win32 helper for the work-combo suite (stdlib only).
//
// Commands:
//
//	gowc.exe scan          print pid|ppid|name|commandline lines (sorted by pid)
//	gowc.exe kill <pid>..  TerminateProcess each PID; prints "killed <pid>" or
//	                       "dead <pid>" (already gone / unopenable). Exit 0.
//	gowc.exe version       print version.
//
// scan reads command lines from the PEB (no powershell/WMI spawn).
// 32-bit targets and protected processes yield an empty command line.
package main

import (
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"unsafe"
)

const gowcVersion = "gowc 1.0.0"

var (
	kernel32                   = syscall.NewLazyDLL("kernel32.dll")
	ntdll                      = syscall.NewLazyDLL("ntdll.dll")
	pOpenProcess               = kernel32.NewProc("OpenProcess")
	pReadProcessMemory         = kernel32.NewProc("ReadProcessMemory")
	pCloseHandle               = kernel32.NewProc("CloseHandle")
	pCreateToolhelp32Snapshot  = kernel32.NewProc("CreateToolhelp32Snapshot")
	pProcess32FirstW           = kernel32.NewProc("Process32FirstW")
	pProcess32NextW            = kernel32.NewProc("Process32NextW")
	pNtQueryInformationProcess = ntdll.NewProc("NtQueryInformationProcess")
	pTerminateProcess          = kernel32.NewProc("TerminateProcess")
)

const (
	th32csSnapProcess       = 0x00000002
	processQueryInformation = 0x0400
	processVMRead           = 0x0010
	processTerminate        = 0x0001
	// x64 offsets (helper is built 64-bit; 32-bit targets read empty).
	pebProcessParametersOff = 0x20
	ruppCommandLineOff      = 0x70
	scanWorkers             = 16
)

type processEntry32W struct {
	size            uint32
	usage           uint32
	processID       uint32
	defaultHeapID   uintptr
	moduleID        uint32
	threads         uint32
	parentProcessID uint32
	priClassBase    int32
	flags           uint32
	exeFile         [260]uint16
}

type processBasicInfo struct {
	reserved1      uintptr
	pebBaseAddress uintptr
	reserved2      [2]uintptr
	uniquePID      uintptr
	reserved3      uintptr
}

type unicodeString struct {
	length        uint16
	maximumLength uint16
	_pad          uint32
	buffer        *uint16
}

type procRow struct {
	pid  uint32
	ppid uint32
	name string
	cmd  string
}

func readMem(h uintptr, addr uintptr, size int) ([]byte, bool) {
	if addr == 0 || size <= 0 || size > 1<<20 {
		return nil, false
	}
	buf := make([]byte, size)
	var done uintptr
	r1, _, _ := pReadProcessMemory.Call(h, addr, uintptr(unsafe.Pointer(&buf[0])), uintptr(size), uintptr(unsafe.Pointer(&done)))
	if r1 == 0 || int(done) != size {
		return nil, false
	}
	return buf, true
}

func readUint64(h uintptr, addr uintptr) (uint64, bool) {
	b, ok := readMem(h, addr, 8)
	if !ok {
		return 0, false
	}
	return *(*uint64)(unsafe.Pointer(&b[0])), true
}

// commandLineOf returns the full command line of pid, or "" when it cannot
// be read (protected process, 32-bit target, or exited mid-scan).
func commandLineOf(pid uint32) string {
	h, _, _ := pOpenProcess.Call(processQueryInformation|processVMRead, 0, uintptr(pid))
	if h == 0 {
		return ""
	}
	defer pCloseHandle.Call(h)

	var pbi processBasicInfo
	r1, _, _ := pNtQueryInformationProcess.Call(h, 0, uintptr(unsafe.Pointer(&pbi)), unsafe.Sizeof(pbi), 0)
	if r1 != 0 || pbi.pebBaseAddress == 0 {
		return ""
	}
	params, ok := readUint64(h, pbi.pebBaseAddress+pebProcessParametersOff)
	if !ok || params == 0 {
		return ""
	}
	raw, ok := readMem(h, uintptr(params)+ruppCommandLineOff, 16)
	if !ok {
		return ""
	}
	us := *(*unicodeString)(unsafe.Pointer(&raw[0]))
	if us.length == 0 || us.buffer == nil {
		return ""
	}
	n := int(us.length) / 2
	wbuf := make([]uint16, n)
	var done uintptr
	r1, _, _ = pReadProcessMemory.Call(h, uintptr(unsafe.Pointer(us.buffer)), uintptr(unsafe.Pointer(&wbuf[0])), uintptr(n*2), uintptr(unsafe.Pointer(&done)))
	if r1 == 0 {
		return ""
	}
	return syscall.UTF16ToString(wbuf)
}

func sanitizeCmd(cmd string) string {
	return strings.ReplaceAll(strings.ReplaceAll(cmd, "\r", " "), "\n", " ")
}

func snapshotEntries() []processEntry32W {
	snap, _, _ := pCreateToolhelp32Snapshot.Call(th32csSnapProcess, 0)
	if snap == uintptr(^uint32(0)) {
		return nil
	}
	defer pCloseHandle.Call(snap)

	var entries []processEntry32W
	var entry processEntry32W
	entry.size = uint32(unsafe.Sizeof(entry))
	r1, _, _ := pProcess32FirstW.Call(snap, uintptr(unsafe.Pointer(&entry)))
	for r1 != 0 {
		entries = append(entries, entry)
		r1, _, _ = pProcess32NextW.Call(snap, uintptr(unsafe.Pointer(&entry)))
	}
	return entries
}

func scan() int {
	entries := snapshotEntries()
	jobs := make(chan processEntry32W, len(entries))
	out := make(chan procRow, len(entries))
	var wg sync.WaitGroup
	for i := 0; i < scanWorkers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for e := range jobs {
				out <- procRow{
					pid:  e.processID,
					ppid: e.parentProcessID,
					name: syscall.UTF16ToString(e.exeFile[:]),
					cmd:  sanitizeCmd(commandLineOf(e.processID)),
				}
			}
		}()
	}
	for _, e := range entries {
		jobs <- e
	}
	close(jobs)
	wg.Wait()
	close(out)

	rows := make([]procRow, 0, len(entries))
	for r := range out {
		rows = append(rows, r)
	}
	sort.Slice(rows, func(i, j int) bool { return rows[i].pid < rows[j].pid })
	for _, r := range rows {
		fmt.Printf("%d|%d|%s|%s\n", r.pid, r.ppid, r.name, r.cmd)
	}
	return 0
}

// kill terminates each PID in-process (the fast equivalent of N taskkill
// calls). PIDs already gone report "dead" -- exit code stays 0 so a single
// stale PID never fails the sweep.
func kill(pids []string) int {
	for _, s := range pids {
		n, err := strconv.ParseUint(s, 10, 32)
		if err != nil || n == 0 {
			fmt.Printf("dead %s\n", s)
			continue
		}
		h, _, _ := pOpenProcess.Call(processTerminate, 0, uintptr(n))
		if h == 0 {
			fmt.Printf("dead %d\n", n)
			continue
		}
		r1, _, _ := pTerminateProcess.Call(h, 1)
		pCloseHandle.Call(h)
		if r1 == 0 {
			fmt.Printf("dead %d\n", n)
			continue
		}
		fmt.Printf("killed %d\n", n)
	}
	return 0
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: gowc.exe scan|kill <pid>..|version")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "scan":
		os.Exit(scan())
	case "kill":
		os.Exit(kill(os.Args[2:]))
	case "version":
		fmt.Println(gowcVersion)
	default:
		fmt.Fprintln(os.Stderr, "usage: gowc.exe scan|kill <pid>..|version")
		os.Exit(2)
	}
}
