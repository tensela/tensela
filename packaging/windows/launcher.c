/* The launcher of the folder of Tensela for Windows: Tensela.exe (the window) and tensela-cli.exe (the terminal).

   It starts the Python of the folder (python\pythonw.exe, or python\python.exe for the terminal) beside itself, in
   isolated mode (-I: it does not read the PYTHON* variables of the computer nor modules from the folder it is opened
   from), with Tensela and the same arguments, waits for it and gives back its code. Nothing else: no job object, no
   console of its own for the window. Built by tools/build_windows.py with the compiler of Visual Studio:

       cl /O2 launcher.c window.res /link /SUBSYSTEM:WINDOWS                     -> Tensela.exe
       cl /O2 /DCONSOLE launcher.c terminal.res /link /SUBSYSTEM:CONSOLE         -> tensela-cli.exe
*/
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>

#ifdef CONSOLE
#define PYTHON L"python.exe"
#define MODULE L"tensela"
#else
#define PYTHON L"pythonw.exe"
#define MODULE L"tensela.ui.launch"
#endif

/* The command line after the name of this program (with its leading space), as Windows gave it. */
static const wchar_t *arguments(void) {
    const wchar_t *line = GetCommandLineW();
    if (*line == L'"') {
        line = wcschr(line + 1, L'"');
        return line ? line + 1 : L"";
    }
    while (*line && *line != L' ' && *line != L'\t')
        line++;
    return line;
}

static int run(void) {
    wchar_t here[32768];
    DWORD length = GetModuleFileNameW(NULL, here, 32768);
    if (length == 0 || length >= 32768)
        return 1;
    wchar_t *slash = wcsrchr(here, L'\\');
    if (slash)
        *slash = 0;
    const wchar_t *rest = arguments();
    size_t size = wcslen(here) + wcslen(rest) + 128;
    wchar_t *command = malloc(size * sizeof(wchar_t));
    if (!command)
        return 1;
    swprintf(command, size, L"\"%ls\\python\\%ls\" -I -m %ls%ls", here, PYTHON, MODULE, rest);
    STARTUPINFOW start = {sizeof(start)};
    PROCESS_INFORMATION process;
    if (!CreateProcessW(NULL, command, NULL, NULL, TRUE, 0, NULL, NULL, &start, &process)) {
#ifdef CONSOLE
        fwprintf(stderr, L"Tensela: could not start %ls\\python\\%ls\n", here, PYTHON);
#else
        MessageBoxW(NULL, L"The Python of this folder is missing: unpack the whole folder again.", L"Tensela",
                    MB_ICONERROR);
#endif
        return 1;
    }
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    free(command);
    return (int)code;
}

#ifdef CONSOLE
int wmain(void) { return run(); }
#else
int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR line, int show) { return run(); }
#endif
