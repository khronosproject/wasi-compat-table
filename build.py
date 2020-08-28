#!/usr/bin/env python3

import glob
import json
import os
import shutil
import subprocess
import tempfile
import textwrap

def run_test(testcmd, testdir, testspec):
    stdin = testspec.get("stdin", None)
    process = subprocess.run(testcmd, cwd=testdir, encoding="utf8", input=stdin, capture_output=True)

    stdout = testspec.get("stdout", None)
    if stdout != None and stdout != process.stdout:
        raise AssertionError(f"Expected stdout to yield {stdout}, got {process.stdout}")

    stderr = testspec.get("stderr", None)
    if stdout != None and stdout != process.stdout:
        raise AssertionError(f"Expected stdout to yield {stdout}, got {process.stdout}")

    returncode = testspec.get("exitCode", None)
    if returncode != None and returncode != process.returncode:
        raise AssertionError(f"Expected process to exit with {returncode}, got {process.returncode}")
    elif returncode == None:
        process.check_returncode()

    return process

def run_deno_test(testmod, testdir, testspec):
    testcmd = ['deno', 'run']

    testcmd.append('--quiet')
    testcmd.append('--allow-all')
    testcmd.append('--unstable')

    with open('.test.deno.ts', 'w') as file:
        file.write(textwrap.dedent('''
          import Context from "https://deno.land/std/wasi/snapshot_preview1.ts";

          const options = JSON.parse(Deno.args[0]);
          const buffer = Deno.readFileSync(Deno.args[1]);

          const pathname = Deno.args[1];
          const context = new Context({
            env: options.env,
            args: [pathname].concat(options.args),
            preopens: options.preopens,
          });

          WebAssembly.instantiate(buffer, {
            wasi_snapshot_preview1: context.exports,
          }).then(function({ instance }) {
              context.memory = instance.exports.memory;
              instance.exports._start();
          });
        '''))

    testcmd.append(os.path.abspath('.test.deno.ts'))

    testcmd.append(json.dumps(testspec))
    testcmd.append(testmod)

    return run_test(testcmd, testdir, testspec)

def test_node(testmod, testdir, testspec):
    testcmd = ['node']

    testcmd.append('--no-warnings')
    testcmd.append('--experimental-wasi-unstable-preview1')
    testcmd.append('--experimental-wasm-bigint')

    with open('.node.js', 'w') as f:
        f.write(textwrap.dedent('''
          const fs = require("fs");
          const { WASI } = require("wasi");

          const options = JSON.parse(process.argv[2]);
          const buffer = fs.readFileSync(process.argv[3]);

          const pathname = process.argv[3];
          const wasi = new WASI({
            env: options.env,
            args: [pathname].concat(options.args],
            preopens: options.preopens,
          });
          WebAssembly.instantiate(buffer, {
            wasi_snapshot_preview1: wasi.wasiImport,
          }).then(function({ instance }) {
              wasi.start(instance);
          });
        '''))

    testcmd.append(os.path.abspath('.node.js'))

    testcmd.append(json.dumps(testspec))
    testcmd.append(filepath)

    return run_test(testcmd, testdir, testspec)

def run_wasmer_test(testmod, testdir, testspec):
    testcmd = ["wasmer", "run"]

    env = testspec.get("env", {})
    for key in env:
        testcmd.append('--env')
        testcmd.append(key + '=' + env[key])

    preopens = testspec.get("preopens", [])
    for path in preopens:
        testcmd.append('--mapdir')
        testcmd.append(path + '::' + preopens[path])

    testcmd.append(testmod)

    args = testspec.get('args', [])
    if len(args) > 0:
        testcmd.append('--')

    for arg in args:
        testcmd.append(arg)

    return run_test(testcmd, testdir, testspec)

def run_wasmtime_test(testmod, testdir, testspec):
    testcmd = ["wasmtime", "run"]

    env = testspec.get("env", {})
    for key in env:
        testcmd.append('--env')
        testcmd.append(key + '=' + env[key])

    preopens = testspec.get("preopens", [])
    for path in preopens:
        testcmd.append('--mapdir')
        testcmd.append(path + '::' + preopens[path])

    testcmd.append(testmod)

    args = testspec.get('args', [])
    if len(args) > 0:
        testcmd.append('--')

    for arg in args:
        testcmd.append(arg)

    return run_test(testcmd, testdir, testspec)

def run_tests(tests, testrunners):
    testresults = {}

    for testmod in tests:
        testresults[testmod] = {}

        with open(testmod.replace(".wasm", ".json"), "r") as file:
            testspec = json.load(file)

        for testcmd in testrunners:
            test = testrunners[testcmd]

            testdir = tempfile.mkdtemp()
            shutil.copytree("tests/fixtures", os.path.join(testdir, "fixtures"), symlinks=True)

            testresult = {
                "status": None,
                "error": None,
            }

            try:
                process = test(os.path.abspath(testmod), testdir, testspec)
                testresult["status"] = "pass"
            except Exception:
                testresult["status"] = "fail"
            finally:
                testresults[testmod][testcmd] = testresult

    return testresults

tests = sorted(glob.glob("tests/*.wasm"))
testrunners = {
  "deno": run_deno_test,
  "node": run_deno_test,
  "wasmer": run_wasmtime_test,
  "wasmtime": run_wasmtime_test,
}

testresults = run_tests(tests, testrunners)

css='''
html {
  box-sizing: border-box;
}

*, *:before, *:after {
  box-sizing: inherit;
}

body {
    background-color: #fff;
    color: #000;
    display: inline-block;
    font-family: 'Open Sans', sans-serif;
    font-weight: 300;
    margin: 0;
    width: 100%;
}

h1 {
    text-align: center;
}

table {
    width: 100%;
}

th {
    font-size: 16px;
    text-align: left;
}

th:first-child {
    text-align: center;
}

.pass {
    color: green;
}

.fail {
    color: red;
}
'''

with open("index.html", "w") as file:
    file.write("<!doctype html>")
    file.write("<html>")
    file.write("<head>")
    file.write("<title>WebAssembly System Interface Compatability Matrix</title>")
    file.write(f"<style>{css}</style>")
    file.write("</head>")
    file.write("<body>")
    file.write("<h1>WebAssembly System Interface Compatability Matrix</h1>")
    file.write("<table>")
    file.write("<thead>")
    file.write("<tr>")
    file.write("<th>Test</th>")

    for testcmd in testrunners:
        file.write(f"<th>{testcmd}</th>")

    file.write("</tr>")
    file.write("</thead>")

    for testmod in testresults:
        file.write("<tr>")
        file.write(f"<td>{testmod}</td>")

        for testcmd in testresults[testmod]:
            testresult = testresults[testmod][testcmd]

            file.write(f"<td class='{testresult['status']}'>")
            file.write(f"{testresult['status']}")
            file.write("</td>")

        file.write("</tr>")

    file.write("</table>")
    file.write("</body>\n")
    file.write("</html>\n")
