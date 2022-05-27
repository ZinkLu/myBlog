---
title: "在Python中调用Go"
date: "2022-05-11T10:45:39+08:00"
draft: false
description: 🐍📞🐭 Python call Go
summary: 在 Python 里面使用 GoSlice GoString Strcut 等，如果时间很多欢迎进来看看
isMath: false
---

# 1. 背景

Go ，编译型语言，性能很好，原生高并发，跨平台，语法简单，有自动GC，相对安全的指针操作。

Python，解释性语言，语法简单，更加贴近英语的书写习惯，不过性能不好，但又因为他的基于C解释器，很容易去和C的库进行通讯，因此也被称为“胶水语言”。

那一个比较合理的场景就是，在关键耗时的算法实现上，使用 Go 编译成库文件，使用 Python 的胶水性质去调用这些库文件进行快速运算，同时再使用 Python 快速编写其他的业务逻辑。

在写本文之前，我一直是这么认为这是一个合理且可行的场景，不过经过实践才发现，其实使用 Python 调用 Go 并没有想象中的这么简单，这瓶“胶水”也没有想象中的这么好用。如果真的遇到一些计算密集型的场景，一个更加合理的做法是将 Go 程序中的算法使用 RPC 或者 HTTP 的服务包一层，使用微服务的形式去进行调用（即使有网络IO也比共享内存来的无痛一些）。当然，如果实在想体验原生的快速，使用 [cython](https://cython.readthedocs.io/en/latest/) 的语法去编写代码然后编译成能被 Python 直接调用的 so 文件才是正道的光。

所以我为什么要使用 Python 调用 Go 呢。

首先，我需要一些算法（基本上就是一些加解密的算法和伪随机数的计算）被编译进一个二进制的文件中（而不是 Python 这种的一眼就能看透的文件）；

其次，我不懂 cython 语法，却熟悉 Go 的编写。(不过在写了这篇文章后，我也学会了一写 cython)

再之，我自己曾经有过调研，使用 Python 成功调用 Go 编译出的 C 静态库，那时候还使用 cython 做了一层桥梁，但实际操作并不复杂；

最后，网上也有一些案例，可以直接用 Python 的 ctypes 包去调用 C 的动态库，连 cython 都省了，多么的方便啊！

好吧，我承认，除了第一、二点是我可能会使用到这个场景的原因，第三、四两点完全是我的自信遮住了我的双眼。

在之前，我看到的一些调用，包括我自己尝试的一些调用，场景都比较简单，无非是 `func add(a int, b int) int` 这种级别的算法，调用起来也是顺利成章。但落实到实际生产中，会发现，连传入和返回一个 `string` 都很复杂。更不要说返回 Go 的 `struct` 和 `slice`了。

所以使用 Python 调用 Go 的这个场景，目前来看并不是不可行，反而我认为是相当可行的，只不过这里面涉及到很多操作和定义都比较原始，也可能会存在内存泄露等等的风险。因此在实际项目的时间、产品的风险上很难去平衡，在这里只记录一下，希望能帮助真的选择了这条路的人。

# 2. 方案简介

我们先来看一下最简单的场景，来确定大体的技术方案。

假设我们就有这么一个函数:

```golang
func add(a int, b int) int {
    return a + b
}
```

需要在 Python 中调用这个函数，第一步：

## 2.1 将 Go 编译成 C 可以调用的库

将 Go 编译成 C 或者 C++ 可调用的库有两种方式，不过大致上，他们都要对这个文件做一些改造：

1. `import "C"` 这个必须要加载 Go 源文件前，这一点必须做，应该就是告诉编译器我要即将编译的软件需要做为 C 的库而不直接是二进制。这个包也提供一些功能让 Go 去直接操作 C 的数据结构等等。

2. `main()` main 函数一定不能少，即使没有任何一行代码也没事；

3. `//export add` 在函数定义之前添加上注释来告诉编译器哪些定义可以被 C 引用，注意 `//` 和 `export` 之前不能有空格，否则会导出失败的。

改造后的代码为：

```golang
// main.go
package main

import "C"

func main() {}

//export add
func add(a int, b int) int {
    return a + b
}
```

接下来，我们有两种方式在 Python 中去调用：

## 2.2 使用 cython 调用静态库

第一种就是将 Go 编译成 C 的**共享静态库**，不过 Python 不能原生调用 C 的静态库，需要使用 Cython、SWIG、Pyrex 做为提供额外的接口。

这里我们使用 Cython ，参考的[这里的文档](https://cython.readthedocs.io/en/latest/src/tutorial/clibraries.html)

1. 首先，将 Go 语言编译成静态库

    ```bash
    go build --buildmode=c-archive -o library.a main.go
    ```

    其中，`--buildmode=c-archive` 告诉 Go 来编译一个静态库，`-o` 是输出文件的名字，这里我们输出为 `library.a`

2. 此时，目录下应该有一个 `library.a` 的文件和 `library.h` 的头文件

    在头文件里面有许多重要的信息，特别的一些结构体和类的定义，当然也包括了我们 export 出来的函数名称；

    ```c
    extern GoInt add(GoInt a, GoInt b);
    ```

    注意这里面的数据类型是 GoInt，不过 GoInt 在上面的头文件里面也定义了，可以看到实际是 C 的 `long long` 类型（和操作系统有关）:
    
    ```c
    typedef long long GoInt64; // GoInt64 对应 C 的长整型
    typedef GoInt64 GoInt; // GO 中 int 类型实际上就是 int64 (64位操作系统)
    ```

    好在 Python 对于 `long long` 类型的处理的处理都为 `int` 因此这里先暂时把他认为就是 Python 中的 `int` ，后面会提到类型的映射；

3. 定义 pxd 文件

    我们遵循 cython 的文档，先创建一个 `external.pxd` 文件，这个文件有点像是 cython 的头文件，我们在里面定义我们即将要应用的包和需要使用到包内的函数：

    ```cython
    cdef extern from "library.h":
        int add(int a, int b) 
    ```

    这样一来，我们就完成了 Cython 头文件的定义，我们引入 library 包，使用里面的 `int add(int a, int b)` 方法。

    不过实际上我们已经比较简化了这个写法，实际上应该这么写：

    ```cython
    cdef extern from "library.h":
        ctypedef int GoInt64
        ctypedef GoInt64 GoInt

        GoInt add(GoInt a, GoInt b)

    ```

4. 定义 pyx 文件

    创建 `external.pyx` 的文件，在这里去定义 Python 的入口

    ```cython
    from external cimport *

    def go_add(a: GoInt, b: GoInt) -> GoInt:
        return add(a, b)
    ```

    GoInt 是我们在前面去定义的，如果没有定义 GoInt 直接写 int 也可以的；

5. setup.py

    最后，我们将创建 `setup.py` 的文件，将刚才编写的 `external.pyx` 文件引入过来，同时，我们将包的名成为 `go_add` ，最后，我们指定本拓展包面向 python3 。

    ```python
    from Cython.Build import cythonize
    from setuptools import Extension, setup

    setup(ext_modules=cythonize(
        [
            Extension(
                name="go_add",
                sources=["external.pyx"],
                extra_objects=['library.a'] # 必须包含 extra_objects 项，否则编译的动态库将找不到对应的库文件
            )
        ],
        language_level=3,
    ), )
    ```

6. build
   
    使用如下命令进行Build，最好检查一下你的目录下，是不是有 `library.a, library.h, external.pxd, external.pyx, setup.py` 的文件了。

    ```
    python setup.py build_ext -i
    ```

    > 如果此时 提示 gcc-5 的命令没有的话，需要先安装 gcc-5 的依赖，具体方法请自行百度。

    随着一阵火花带闪电，我们成功得生成了 build 的文件夹，此时对我来说，目录如下所示：

    ```bash
    .
    ├── build
    │   ├── lib.linux-x86_64-3.8
    │   │   └── go_add.cpython-38-x86_64-linux-gnu.so
    │   └── temp.linux-x86_64-3.8
    │       └── external.o
    ├── external.c
    ├── external.pxd
    ├── external.pyx
    ├── go_add.cpython-38-x86_64-linux-gnu.so
    ├── library.a
    ├── library.h
    ├── main.go
    └── setup.py
    ```

    可以看到，`external.c` 文件和 `go_add.cpython-38-x86_64-linux-gnu.so` 这两个文件是 cython 在 build 过程中自动生成的。

    build 文件夹下，`lib.$操作系统-$架构-$Python版本` 的文件夹和 `$包名.cpython-$python版本-$架构-$操作系统.so` 的文件。

    所以此时你必须保证操作系统、操作系统架构、Python版本都能对的上才能继续下面的步骤。

7. import

    由于我们没有 install，做临时测试，因此我们直接 `cd build/lib.linux-x86_64-3.8` 下，直接输入 `python` 打开交互式窗口：

    ```shell
    Python 3.8.13 (default, Mar 16 2022, 13:02:57) 
    [GCC 5.4.0 20160609] on linux
    Type "help", "copyright", "credits" or "license" for more information.
    >>> import go_add
    >>> go_add.go_add(100000, 10000)
    110000
    >>
    ```

    > 操作系统、操作系统架构、Python版本 有一个对不上都不能 import ，前两个还好说，如果此时的环境变量有问题，进入的是 python2.7 或者是 python3.10 等其他版本，都不会成功

## 2.3 使用动态库

还有一种是将 Go 编译成 `so/dll` 的动态库，可喜可贺的是，在这种方式下，Python 内置的 `ctypes` 可以去直接调用。

1. 编译动态库
   
    ```bash
    go build --buildmode=c-shared -o library.so main.go
    ```

    类似的，当前目录下回有一个 `library.so` 和 `library.h` 的文件

2. 编写 `main.py`

    ```python
    import ctypes

    lib = ctypes.cdll.LoadLibrary("library.so")

    print(lib.add(1, 2))
    ```

    使用 `ctypes.cdll.LoadLibrary` 来加载这个动态库，然后就可以直接调用了。

3. 确定函数的参数和返回值

    在 `int add(int, int)` 这个函数中，我们是明确知道返回值的，并且，在 `.h` 的头文件中，我们也只能明确看到这个函数的签名的，但在 Python 调用者这边，却感觉想盲盒一样，并不知道参数的类型和返回值的类型，在 int 这种基本类型上还好说一些，如果碰到其他的数据类型，则 Python 会不知道怎么处理这个返回值。

    所以我们应该去告诉 Python 这个函数的签名，做的事情其实就有点像在 `pxd` 文件中定义签名类型。

    ```python
    import ctypes
    
    lib = ctypes.cdll.LoadLibrary("library.so")
    
    GoInt64 = ctypes.c_int64
    GoInt = GoInt64
    
    add = lib.add
    
    add.argtypes = [GoInt64, GoInt64]
    add.restype = GoInt64
    
    res = add(GoInt(1), GoInt(2))
    
    print(res)
    ```

    我们严格遵循了函数签名，定义了 Python 版本的 GoInt 和 GoInt64。

其实，在调用 Go 的函数时，更多的就是去处理参数和返回值的类型，下面我们就来看看 Go 的类型是如何和 Python 类型做转换的；

# 3. Number

Int 类型我们在上面已经说了，下面我们以 64 位的系统为准，罗列一下数字类型中 Python - C - Go 的类型转换。

> 在 Python 的 ctypes 的文档中已经罗列了许多类型了，详细可以参考下 [这里](https://docs.python.org/3/library/ctypes.html#fundamental-data-types)

| ctypes       | Python         | C                                      | Go.h             | Go                    |
| ------------ | -------------- | -------------------------------------- | ---------------- | --------------------- |
| c_bool       | bool           | _Bool                                  | bool             | bool                  |
| c_byte       | int            | char                                   | GoInt8           | int8                  |
| c_ubyte      | unsigned char  | int                                    | GoUint8          | uint8                 |
| c_short      | short          | int                                    | GoInt16          | int16                 |
| c_ushort     | unsigned short | int                                    | GoUint16         | uint16                |
| c_int        | int            | int                                    | GoInt32          | int32                 |
| c_uint       | int            | unsigned int                           | GoUint32         | uint32                |
| c_ulong      | int            | unsigned long                          | GoUint32         | uint32                |
| c_longlong   | int            | __int64 or long long                   | GoInt64 or GoInt | int64 or int          |
| c_ulonglong  | int            | unsigned __int64 or unsigned long long | GoUint64         | uint64                |
| c_size_t     | int            | size_t `__SIZE_TYPE__`                 | GoUintptr        | uintptr               |
| c_ssize_t    | int            | ssize_t or Py_ssize_t                  | Go中无定义       |                       |
| c_float      | float          | float                                  | GoFloat32        | float32               |
| c_double     | float          | double                                 | GoFloat64        | float64               |
| c_longdouble | float          | long double                            | GoFloat64        | float64               |
| 无定义       | float          | float _Complex                         | GoComplex64      | complex64             |
| 无定义       | float          | double _Complex                        | GoComplex128     | complex128 or complex |

可以看到，Python 的 int 和 float 能解决所有的数字类型，因此在大多是时候，Go 函数中返回的数字类型都可以使用 int 和 float 来接，上述的代码可以改为：

```python
add = lib.add

add.argtypes = [int, int]
add.restype = int
```

返回值写成 int 是没问题的，因为 Python 的 int 有点海纳百川的意思，入参的时候虽然是 int 类型，不过在函数实际处理时，会把超过实际类型的数字给**截断**，因此还是建议仔细处理入参

```python
res = add(1 << 63, 0) # GoInt 是不能达到 1<<63的，所以这个直接被截断了

print(res)
>>> 0
```

对于 Go 中的 Complex 的数据类型，在 ctypes 中没有定义，可以使用 Python 的 Float 去处理，经过我的测试，float 的精度是不会丢失的。不过如果要参与后续的计算，并且还要关心精度的问题，就考虑使用 Python 的 Decimal。

当然，也可以在 cython 用 `complex.h` 中的数据结构进行处理，总之对精度有要求还是要尽可能得去处理成 Decimal。

```cython
cdef extern from "complex.h":
    ctypedef long double GoComplex128
```

# 4. String

刚才还是一个比较简单的场景，都是以数字来回，换做是字符串的话，情况又有不些不一样了。

让我们先看看 `Go.h` 中 GoString 的定义:

```c
typedef struct { const char *p; ptrdiff_t n; } _GoString_;
```

首先有一个 p 的指针变量，指向一个 char，随后是 ptrdiff_t 类型的 n 变量。

ptrdiff_t 类型实际上是一个长整型，他在 `stddef.h` 中被定义，它被用来表示两个指针变量做减法的结果，结果等于两个同类型指针之间包含的指针数量。

因此这个 n 变量就代代表字符串的长度。这么说并不准确，应该是字节的长度，因为 C 中并不存在 Unicode 类型，因此必须把字符串进行编码。

让我们看下 Python 对象和 C 字符相关的转换

| ctypes    | Python               | C                         |
| --------- | -------------------- | ------------------------- |
| c_char    | 长度为1的bytes       | char                      |
| c_wchar   | 长度为1的string      | wchar_t                   |
| c_char_p  | bytes object or None | char* (NUL terminated)    |
| c_wchar_p | string or None       | wchar_t* (NUL terminated) |
| c_char    | 长度为1的bytes       | char                      |

## 4.0 准备

先在 `main.go` 文件中添加一个函数作为我们调用的对象

```go
// main.go
package main

import "C"

//export hello
func hello(a string) {
	fmt.Printf("hello %s \n", a)
}
```

然后重新build一下，我们暂时还是在 cython 中使用 c-archive ，在 Python 中 使用 c-share。

```bash
go build -buildmode=c-shared -o library.so main.go
go build -buildmode=c-archive -o library.a main.go
```

## 4.1 cython 中使用字符串

1. 先定义 pxd 文件

    ```cython
    # external.pxd
    cdef extern from "stddef.h":
        cdef struct _GoString_:
            const char *p
            ptrdiff_t n
        
        ctypedef _GoString_ GoString
        void hello(GoString a)
    ```

2. 定义 pyx 文件

    定义 cdef 方法，将一个 `char*` 转换成 `GoString` ，而 `char*` 可以对应 Python 中的 bytes。

    ```cython
    # external.pyx
    from external cimport hello, GoString
    
    cdef (GoString) getGoString(char* string):
        cdef GoString goStr # 创建一个 GoString 对象
        goStr.p = string # 设置p值
        goStr.n = len(string) # 设置n值
        return goStr
    
    def go_hello(a: str):
        return hello(getGoString(a.encode())) # bytes 就等于 char*
    ```

## 4.2 ctypes 中的字符串

在 ctypes 中，`c_char_p` 可以来代表一个 bytes 对象，所以看一下 `c_char_p` 的用法。

其实你估计也应该看出来了， `c_char_p` 是一个指针对象，和 `ctypes.pointer` 一样，不过我们再下一节会说下指针的用法。

1. 定义 GoString

    我们用 ctypes 定义一个 c 中的结构体，其实也很容易。

    ```python
    # main.py
    from ctypes import Structure, c_char_p, c_int64, cdll

    class GoString(Structure):
        _fields_ = [
            ("p", c_char_p),
            ("n", c_int64),
        ]
    ```

2. 加载库并调用

    ```python
    # 接着上面
    __library = cdll.LoadLibrary('library.so')
    hello = __library.hello
    hello.argtypes = [GoString]
    hello.restype = None
    string = "Python"
    hello(GoString(string.encode(), len(string.encode())))
    ```

    ```bash
    python main.py
    hello Python
    ```

## 4.3 在 Go 中返回 string

如你所见，GoString 是一个结构体，它又一个指针变量和一个 int 变量，因此在 Go 中如果想返回 String，是不允许的，不然可以试一下

```go
// main.go
package main

import "C"

//export hello
func hello(a string) string {
	return fmt.Sprintf("hello %s \n", a)
}
```

编译

```bash
go build -buildmode=c-shared -o library.so main.go
```

Python调用

```python
from ctypes import Structure, c_char_p, c_int64, cdll


class GoString(Structure):
    _fields_ = [
        ("p", c_char_p),
        ("n", c_int64),
    ]

__library = cdll.LoadLibrary('library.so')
hello = __library.hello
hello.argtypes = [GoString]
hello.restype = GoString # 将hello的返回类型设置为 GoString

string = "Python"

print(hello(GoString(string.encode(), len(string))))
```

运行

```bash
python main.py
panic: runtime error: cgo result has Go pointer
goroutine 17 [running, locked to thread]:
panic({0x105482780, 0x14000112230})
        /opt/homebrew/Cellar/go/1.18.2/libexec/src/runtime/panic.go:941 +0x3d8
runtime.cgoCheckArg(0x10547fb80, 0x14000112220, 0x10?, 0x0, {0x10545b848, 0x19})
        /opt/homebrew/Cellar/go/1.18.2/libexec/src/runtime/cgocall.go:522 +0x428
runtime.cgoCheckResult({0x10547fb80, 0x14000112220})
        /opt/homebrew/Cellar/go/1.18.2/libexec/src/runtime/cgocall.go:638 +0x68
_cgoexp_df0a212b41c1_hello(0x16b5fe3a0)
        _cgo_gotypes.go:70 +0xa0
runtime.cgocallbackg1(0x1054573e0, 0x0?, 0x0)
        /opt/homebrew/Cellar/go/1.18.2/libexec/src/runtime/cgocall.go:314 +0x248
runtime.cgocallbackg(0x0?, 0x0?, 0x0?)
        /opt/homebrew/Cellar/go/1.18.2/libexec/src/runtime/cgocall.go:233 +0xd8
runtime.cgocallbackg(0x1054573e0, 0x16b5fe3a0, 0x0)
        <autogenerated>:1 +0x1c
runtime.cgocallback(0x0, 0x0, 0x0)
        /opt/homebrew/Cellar/go/1.18.2/libexec/src/runtime/asm_arm64.s:1185 +0xa0
runtime.goexit()
        /opt/homebrew/Cellar/go/1.18.2/libexec/src/runtime/asm_arm64.s:1263 +0x4
[1]    81130 abort      python main.py
```

在 Go 中不允许返回 Go 的 pointer，因此我们需要换一种方式来返回 string，使用 go 的 C 包中提供的方法。

```go
//export hello
func hello(a string) *C.char {
	return C.CString(fmt.Sprintf("hello %s\n", a))
}
```

再进一步，其实我们可以将入参也改了

```go
//export hello
func hello(a *C.char) *C.char {
	var str string = C.GoString(a)
	return C.CString(fmt.Sprintf("hello %s\n", str))
}

```

这样的话，就可以在 Python 里面这样使用了。

```python
from ctypes import c_char_p, cdll

__library = cdll.LoadLibrary('library.so')
hello = __library.hello
hello.argtypes = [c_char_p]
hello.restype = c_char_p

string = "Python"

res = hello(string.encode())

print(res)
```

其实字符串已经不是很方便了，至少在需要在 go 文件中对 export 的函数进行返回值的改造。

不过谁让我们选择了这条路呢，继续

# 5. Struct

对于 string 来说，它是 Go 内置的类型，可以被导出到 C 的结构体，但目前无法使用 Go 自带的结构体，也不能 export Go的结构体，
这意味下面的代码是无法编译的

```go
package main
import "C"

type Person struct {
	name string
	age  int
}

//export helloPerson
func helloPerson(p Person) {
	p.sayHello("hello")
}
```

所以使用基本类型去进行调用才是正道的光。

## 5.1 结构体作为参数

如果非要使用结构体，只能使用 C 结构体作为中间桥梁，链接 Python 和 Go。

```go
package main

/*
struct Person {
char* name;
long long age;
};
*/
import "C"

type Person struct {
    name string
    age  int
}

func (p Person) sayHello(sayWhat string) {
    fmt.Printf("person %s saying %s", p.name, sayWhat)
}

//export helloPerson
func helloPerson(p C.struct_Person) {
    var person Person = Person{C.GoString(p.name), int(p.age)}
    person.sayHello("hello")
}

```

> 对于 C.struct_Person ，IDE 是会提示的，我用的 vscode 就完美检测出了在 Go 中定义的 C 结构体

在编译后，可以看到 library.h 中已经为我们定义好了结构体 Person，当然还有 helloPerson 的函数签名。

接下来，我们应该在 Python 中调用了。

1. cython

    ```cython
    # pxd
    cdef extern from "library.h":
        cdef struct Person:
            char* name
            int age

        void helloPerson(Person p)
    ```

    ```cython
    # pyx
    import cython
    from external cimport Person, helloPerson
    
    cdef (Person) getPerson(char* name, int age):
        cdef Person p
        p.name = name
        p.age = age
        return p

    def go_person(name: str, age: int):
        cdef Person p = getPerson(name.encode(), age)
        helloPerson(p)
    ```

    当然上述方法可以合并到一个 Cython 的方法中
    
    ```cython
    def go_person(name: str, age: int):
        cdef Person p
        name_bytes = name.encode()
        p.name = name_bytes
        p.age = age
        helloPerson(p)
    ```

2. Python

    对于 Python 来说，我们刚才在定义字符串的时候也可以知晓了，使用 Structure 来处理

    ```python
    from ctypes import (POINTER, Structure, pointer, c_char_p, c_int)
    class Person(Structure):
        _fields_ = [
            ("name", c_char_p),
            ("age", c_int),
        ]
    
    __library = cdll.LoadLibrary('library.so')
    hello_person = __library.helloPerson
    hello_person.argtypes = [Person]
    
    hello_person(
        Person(name=b"xiaoming", age=12)
    )
    ```

## 5.2 结构体作为返回值

对于结构体来说，返回值的处理和入参是一样的，让我们稍微修改一下 go 中函数的实现：

```go
package main

/*
struct Person {
char* name;
long long age;
};
*/
import "C"

type Person struct {
    name string
    age  int
}

func (p Person) sayHello(sayWhat string) {
    fmt.Printf("person %s saying %s", p.name, sayWhat)
}

//export helloPerson
func helloPerson(p C.struct_Person) C.struct_Person {
    var person Person = Person{C.GoString(p.name), int(p.age)}
    person.sayHello("hello")
    return C.struct_Person{C.CString("xiaohong"), 12}
}
```

这里拿 ctypes 举例，cython 同理就不赘述了。

```python
hello_person = __library.helloPerson
hello_person.argtypes = [Person]
hello_person.restype = Person

p = hello_person(
    Person(name=b"xiaoming", age=12)
)
print(p.name, p.age)
# xiaohong, 12
```

## 5.3 问题

我一开始是这么定义 Person 结构体的

```go
struct Person {
    char* name;
    int age;
};
```

age 使用的是 int 型，不过在 Go 中，它生成的 C_Struct 却是这样的

```go
type _Ctype_struct_Person struct {
	name	*_Ctype_char
	age	_Ctype_int
	_	[4]byte
}
```

莫名其妙多了一个 `_` 变量，而且还是一个 4 个字节的数组，但是换成 `long long` 后，这个变量又没了。然后我又换成了 `short` 结果这个数组变成 6 个字节了。

我猜测是 Go 中为了兼容 int 溢出的问题的？4 个字节保存一个 int32 的数字，int 本身就是 4 个字节，在 64 位的电脑上他们加一起正好是 Go 中 int 的大小。

# 6. Pointer

从这里开始，就有点危险的意思了，本来在 Python 中是不存在指针操作的，但是我们可以给 Go 传一个指针地址，也能接 Go 的一个指针地址作为返回值。

地址是一个 `int` 类型的变量，记录了变量在内存的地址

| ctypes    | Python | C                     | Go.h      | go      |
| --------- | ------ | --------------------- | --------- | ------- |
| c_size_t  | int    | size_t                | GoUintptr | uintptr |
| c_ssize_t | int    | ssize_t or Py_ssize_t | GoUintptr | uintptr |

## 6.0 基本类型指针

1. 传入一个指针

    ```go
    //export changeInt
    func changeInt(a *int) {
        rand.Seed(time.Now().Unix())
        *a = rand.Int()
        println(*a)
    }
    ```

    ```python
    __library = cdll.LoadLibrary('library.so')

    change_int = __library.changeInt
    change_int.argtypes = [POINTER(c_int64)]

    i = pointer(c_int64(100))
    change_int(i)
    print(i.contents)
    ```

    运行这个程序会发现 i 的值已经被改变了，其实就是 Go 直接操作了指针指向的内存区域的。

2. 返回一个指针

    直接返回 Go 的指针 `*a` 是不被允许的，这里应该是返回 uintptr 类型，代表的是一个指针所指向的地址，然后我们在 Python 中再构造这个指针对象，从地址中获取值。

    为了获取 Go 变量的地址，我们使用 `unsafe.Pointer`

    ```go
    //export helloPersonPoint
    func helloPersonPoint(p *C.struct_Person) uintptr {
        var cPerson C.struct_Person = C.struct_Person{C.CString("xiaohong"), 12}
        var ptr uintptr = uintptr(unsafe.Pointer(&cPerson))
        println(ptr)
        return ptr
    }
    ```

    在 Python 和 Cython 中，我们可以通过轻松将一个地址转换成指针对象：

    cython 的转换不复杂，不过对于指针的取值有点迷，如果是 C 语言，对一个指针取值为 `*pointer`，而 cython 中，对指针取值为 `pointer[0]`

    > 当然，`pointer[1]` 这种操作也是可以的，他会直接取下一个指针的值，在我们当前的场景下这么操作非常危险；

    ```cython
    # pyx 
    # 记得在 pxd 文件中定义 returnIntPointer 和 GoUintptr
    
    cdef GoInt return_int_pointer(GoInt a):
        cdef GoUintptr res_addr = returnIntPointer(&a)
        cdef GoInt* res = <GoInt*> res_addr
        return res[0]
    
    def go_return_int_pointer(a: int):
        res = return_int_pointer(a)
        print(res)
    
    ```

    python ctypes 对于指针的转换也是方便:

    ```python
    # py
    __library = cdll.LoadLibrary('library.so')
    
    change_int = __library.returnIntPointer
    change_int.argtypes = [POINTER(c_int64)]
    change_int.restype = c_size_t
    
    i = pointer(c_int64(100)) # i 是 pointer 类型的参数
    res_addr = change_int(i) # res_addr 是 一个地址
    res = cast(res_addr, POINTER(c_int64)) # 将地址转换为一个指针对象
    print(res.contents)
    print(res[0])  # 和 cython 一样， Python 也允许这样取指针的值
    ```

通过上面两个例子也清楚了该怎么处理指针返回值了，同时，Python 对指针的操作也让我们能够应对接下来的数组。

## 6.1 结构体指针

虽然返回的是一个 C struct 的一个指针，不过这还属于 Go 指针的范畴，Cgo 是不允许返回任何 Go 的指针对象的(会影响垃圾回收)，因此我们需要进一步改进，让 Go 直接返回一个内存地址。

下面这种也是不允许的

```go
//export helloPersonPoint
func helloPersonPoint(p *C.struct_Person) *C.struct_Person {
	var name = C.CString("xiaohong")
	var age = C.longlong(12)
	var cPerson C.struct_Person = C.struct_Person{name, age}
	return &cPerson
}
```

如果想返回一个指针，我们应该和上面一样，返回 uintptr，不过这里 uintptr 可能有问题。

让我们先返回一个 `C.size_t`，后面我们会讨论到 uintptr 有哪些原因。

```go
package main

/*
struct Person {
	char*   name;
  	long long age;
};
*/
import "C"

//export helloPersonPoint
func helloPersonPoint(p *C.struct_Person) C.size_t {
	var name = C.CString("xiaohong")
	var age = C.longlong(12)
	var cPerson C.struct_Person = C.struct_Person{name, age}
	var ptr C.size_t = C.size_t(uintptr(unsafe.Pointer(&cPerson)))
	return ptr
}
```

编写调用程序

1. cython

    ```cython
    # pxd
    cdef extern from "library.h":
        cdef struct Person:
            char* name
            long long age
    
        size_t helloPersonPoint(Person* p)
    ```

    ```cython
    cdef (Person) getPerson(char* name, int age):
        cdef Person p
        p.name = name
        p.age = age
        return p
    
    def go_person_point(name: str, age: int):
        cdef Person p = getPerson(name.encode(), age)
        cdef size_t pAddress = helloPersonPoint(&p)
    
        cdef Person* p2 = <Person*> pAddress
        print(p2.name)
        print(p2.age)
    ```


2. python
   
    对于 Python 来说，有一个 POINTER 的类型可以用来接受指针对象，有 cast 方法，可以将地址转换成响应的指针对象。

    ```python
    class Person(Structure):
        _fields_ = [
            ("name", c_char_p),
            ("age", c_longlong),
        ]
    
    hello_person_point = __library.helloPersonPoint
    
    hello_person_point.argtypes = [POINTER(Person)]
    hello_person_point.restype = c_size_t
    
    p_addr = hello_person_point(pointer(Person(name=b"xiaoming", age=12)))
    
    person_pointer = cast(p_addr, POINTER(Person))
    
    person = p_pointer.contents # contents 是指向指针的值
    print(person.name)
    print(person.age)
    ```

## 6.2 数组指针

对于 Cgo 来说，它几乎不支持对 Go 原生数组的操作。

| 类型             | 参数/返回 | 是否允许         |
| ---------------- | --------- | ---------------- |
| 数组             | 参数      | 不允许           |
| 数组             | 返回      | 不允许           |
| 数组指针         | 参数      | 不允许           |
| 数组指针（地址） | 返回      | 允许（但有问题） |

因此我们还是要借助 C 的 Array 来完成这种操作。

1. 编写 Go 代码

    ```go
    //export returnIntArray
    func returnIntArray(first *int, length int) uintptr {
        // #1
        const buffer = 1024
        if length > buffer {
            fmt.Println("array must not great than %s \n", buffer)
        }
        goArray := (*[buffer]int)(unsafe.Pointer(first)) // #2
        var goSlice []int = goArray[:length] // #3
        fmt.Println(goSlice)
    
        last := length - 1
        goSlice[0], goSlice[last] = goSlice[last], goSlice[0] // #4
    
        const arrayLength = 10
        ret := C.malloc(C.size_t(arrayLength) * C.size_t(unsafe.Sizeof(C.longlong(0)))) // #5
        pRet := (*[arrayLength]C.longlong)(ret) // #6
        for i := 0; i < 10; i++ {
            pRet[i] = C.longlong(i)
        }
        return uintptr(ret) // #7
    }
    ```

    先解释一下这个代码。
    
    1. 由于 Cgo 不允许直接入参数组，所以我们传入一个 int 指针，代表数组的第一个元素，length 代表了数组的长度；

    2. Go 里面和 C 一样，可以直接将 Pointer cast 成另外的一种类型，这里，我们将指针转换成了 `[1024]int` 的数组。需要注意的是，`[length]int` 是不行的，因为 length 是变量，Go 不允许申请一个不定长的数组；
    
    3. 因此我们使用一个 1024 长度的 buffer 先去构建一个数组，然后转换成切片；
    
        需要注意的是，我们无法直接使用 Pointer 转换一个 Slice 的，因为 Go 不知道 Slice 的 len 和 cap，如果让他去转，他会直接转成一个长度为 0 的 Slice；
    
    4. 我们直接操作数组，交换两个值，这样我们能比较直观看到结果；
    
    5. 使用 C.molloc 申请一片内存空间，大小为，`数组的长度 * 数组元素大小` (这里是 C.longlong)，返回的是一个指针对象，这个内存是不会被 Go GC 的；
    
    6. 然后我们需要将指针转换为 Go 中的 array，以便操作，我们塞入几个数字到数组中；
    
    7. 返回这个地址；

我们来编写调用方

2. Cython

    Cython 创建数组可以使用 cpython 的 array，见[文档](https://cython.readthedocs.io/en/latest/src/tutorial/array.html)

    同时，在 Cython 里面操作指针和索引操作一样。

    ```cython
    # pxd
    cdef extern from "library.h":
        ctypedef int GoInt64
        ctypedef GoInt64 GoInt 
        ctypedef size_t GoUintptr
        GoUintptr returnIntArray(GoInt* first, GoInt length)
    ```

    ```cython
    # pyx
    from cpython cimport array
    from external cimport GoInt, GoUintptr, returnIntArray

    import array
    from typing import List

    def go_return_int_array(youArray: List[int]):
        cdef GoInt[:] carray = array.array("q", youArray)
        cdef GoInt *carray_p = &carray[0]
        cdef GoUintptr res_addr = returnIntArray(carray_p, len(youArray))
        cdef GoInt *res = <GoInt*> res_addr # 返回的结果，先转化成一个指针
        print(carray.base) # 这里是 memoryview 对象，我们可以直接获取他内部的对象，或者直接操作 memoryview，也很方便
        print([res[i] for i in range(10)]) # 打印返回的结果，我们操作指针移动 10 次，去取值
        return carray
    ```

3. Python

    在 Python 里面操作指针和索引操作一样。

    ```python
    import array
    from ctypes import (POINTER, cdll, c_int64)
    
    __library = cdll.LoadLibrary('library.so')
    
    return_int_array = __library.returnIntArray
    
    length = 10
    args_type = POINTER(c_int64) * length # Python 中为了创建一个 C 的数组，需要先创建一个 POINTER 的类型，然后再 乘一个长度，即可获得 C 中的数组了
    res_type = POINTER(c_int64) # 返回值是一个指针
    
    return_int_array.argtypes = [args_type, c_int64]
    return_int_array.restype = res_type
    
    arr = array.array("q", range(length))
    res = return_int_array(args_type.from_buffer(arr), length) # 使用 from_buffer 速度比较快，还有一种方式是 args_type([1,2,3,4])，这种速度会比较慢，Python 的 array 是更为底层的数据结构
    # res = return_int_array(args_type(list(range(length))), length) # 慢
    print(arr) # 打印了 array 会发现已经被改动
    print([res[r] for r in range(10)])  # 以索引的方式去操作指针
    ```

其实在 Go 中返回数组时时，更多的是在编写 C 的代码了，感觉真的挺复杂的。不过也不需要担心，后面的 Slice 会 *稍微* 方便一点。

## 6.3 问题

1. Cython 的问题 

    我这里发现一个问题，还是以上面的代码为例
    
    如果再 getPerson 中返回 Person 的指针，即 `Person*` ，在 go_person 中再调用 helloPerson 可能有问题，如下所示：

    ```cython
    cdef (Person*) getPerson(char* name, int age):
        cdef Person p
        p.name = name
        p.age = age
        return &p

    def go_person(name: str, age: int):
        cdef Person* p = getPerson(name.encode(), age)
        helloPerson(p)  #  在 Go 中打印不出名字，并且在本函数中也无法打印
    ```

    在函数中打印后发现实际上 p 中的 name 和 age 都是是零值，不清楚是怎么一回事。

2. 为什么 Struct 不直接返回 uintptr

    可能会有人好奇，为什么不直接返回 uintptr ，理论上来说不一样吗？

    确实，在数据类型上，uintptr 和 `C.size_t` 应该是一样的。不过使用 uintptr 直接返回又有问题，大家可以改一下试试看。
   
    改完以后，使用 Python 调用，发现，name 是不正常的，但是 age 是正常的（在我的 x86 的机器上都不正常，name 干脆是乱码）。

    我还尝试编写了 C 的代码去进行调用，一样会有问题：

    ```c
    #include <stdio.h>
    #include <stdlib.h>
    #include "library.h"

    size_t getPerson()
    {
        struct Person *p = malloc(sizeof(struct Person));
        p->name = "xiaoming";
        p->age = 12;
        printf("%s\n", p->name);
        printf("%d\n", p->age);
        return (size_t)p;
    }

    void testPerson()
    {
        size_t t = getPerson();
        struct Person *p = (struct Person *)t;

        GoUintptr got = helloPersonPoint(p);
        struct Person *gop = (struct Person *)got;

        printf("%s\n", gop->name);
        printf("%lld\n", gop->age);
    }

    int main()
    {
        testPerson();
    }

    ```

    我猜测可能原因是，使用 uiniptr 类型后，Go 对象(在这里是 C.struct_Person 实例)的指针的还是由 Go 来管理，因此 Go 会对它进行 GC，一旦触发了 GC 那么可能会导致一些问题。

    如果是构建了 `C.size_t` 后，由 C 程序来管理指针，Go 就无法进行 GC。

    还有一个原因可以支撑我这个猜测，为什么我们先定义了 name 和 age 的 C 变量，如果直接使用 Go 的对象去构建 C.struct_Person ，也会造成奇怪的问题，如下：

    ```go
    func helloPersonPoint(p *C.struct_Person) C.size_t {
        var cPerson C.struct_Person = C.struct_Person{C.CString("xiaohong"), C.longlong(12)}
        var ptr C.size_t = C.size_t(uintptr(unsafe.Pointer(&cPerson)))
        return ptr
    ```

    此时我再调用后的结果为

    ```bash
    b'xiaohong'
    1374389544576
    ```

    有可能临时变量和触发 GC 有关？当然我完全是瞎猜乱猜，后面有机会可以提一个 issue 去请教一下。

3. 为什么不直接返回 GoArray 的 uintptr

    在 [6.2 数组指针](#62-数组指针) 这一章节，使用 `C.malloc` 申请了一波内存空间，然后在对内存进行操作。

    不直接返回 GoArray 的原因和第二点一样，因为 GoArray 是 Go 的内置类型，由 Go 管理其指针，所以可能也触发了 Go 的 GC。

    总之，直接返回 GoArray 的地址，然后在 C 或者 Python 中操作指针是会产生 segment fault 的，必须用 C 的 malloc API 去申请一片不会被回收的内存。

    如果有人想试试，可以参考下面的代码

    ```go
    //export returnWrongIntArray
    func returnWrongIntArray() uintptr {
        a := [10]C.longlong{}
        for idx, v := range a {
            a[idx] = C.longlong(v)
        }
        return uintptr(unsafe.Pointer(&a))
    }
    ```

    可以保证的是，在操作指针的时候一定会出现意想不到的值，并且还有可能直接 segment fault。

# 7. Slice

终于到了 Slice，其实 Slice 和 GoString 一样，他都是个结构体:

```c
typedef struct { void *data; GoInt len; GoInt cap; } GoSlice; // .h 文件不会展示出 Slice 中真正的数据结构，因此还是需要结合
```

因此 Slice 作为参数的话，只要在 Python 中定义结构体就能完成，只不过在 Go 中 return 一个 Slice 可能有点不太友好，我们还是要想办法给他转换成地址再返回。

| 类型     | 参数/返回 | 是否允许 |
| -------- | --------- | -------- |
| 切片     | 参数      | 允许     |
| 切片     | 返回      | 不允许   |
| 切片指针 | 参数      | 允许     |
| 切片指针 | 返回      | 允许     |

除了无法不能直接返回一个 GoSlice 的对象外，Cgo 对其他情况的支持还算比较友好，不过 Slice 在 Go 中本来就是引用类型，*Slice 和 Slice 都是一样的，因为它直接操作的 Slice 中的 data 指针（其实不完全是）。

1. 定义函数
   
   ```go
    //export returnIntSlice
    func returnIntSlice(slice []int, slicePoint *[]int) uintptr {
        for idx, _ := range slice {
            slice[idx] = idx
        } // # 1
   
        for idx, _ := range *slicePoint {
            (*slicePoint)[idx] = idx
        } // # 2
   
        res := make([]int, 10, 10) // # 3
        for idx, _ := range res {
            res[idx] = idx
        }
   
        sh := (*reflect.SliceHeader)(unsafe.Pointer(&res)) // # 4
        return sh.Data // # 5
    }
   ```

   1. 对 `[]int` 类型的参数进行修改

   2. 对 `*[]int` 类型的参数进行修改

   3. 创建一个 `[]int`，它的 cap 和 len 都是 10
   
   4. 我们先拿到 `[]int` 的地址，再通过反射拿到切片对应的 Struct

   5. 返回 Slice 中的 Data（即地址），由于还是返回的是 Go 管理的地址，因此这样做是有问题的（参考 array 的返回方式，我实在是懒得写了）；

2. Cython

    Cython 的操作几乎和 array 一样，只不过是要多构建一个 GoSlice 的结构体罢了

    ```cython
    # pxd
    cdef extern from "library.h":
        ctypedef int GoInt64
        ctypedef GoInt64 GoInt
        ctypedef size_t GoUintptr
        cdef struct _GoSlice:
            void *data
            GoInt len
            GoInt cap
        ctypedef _GoSlice GoSlice
        GoUintptr returnIntSlice(GoSlice slice, GoSlice* slicePoint)
    ```

    ```cython
    # pyx
    def go_return_int_slice(youSlice: List[int]):
        cdef GoInt[:] carray = array.array("q", youSlice)
        cdef GoInt *carray_p = &carray[0]
        cdef GoSlice s1
        s1.data = carray_p
        s1.cap = len(youSlice)
        s1.len = len(youSlice)

        cdef GoInt[:] carray2 = array.array("q", youSlice)
        cdef GoInt *carray_p2 = &carray2[0]
        cdef GoSlice s2
        s2.data = carray_p2
        s2.cap = len(youSlice)
        s2.len = len(youSlice)

        cdef GoUintptr res_addr = returnIntSlice(s1, &s2)

        cdef GoInt *res = <GoInt*> res_addr

        print(res_addr)
        print(carray.base) # carray 已经被修改
        print(carray2.base) # carray2 也被修改了
        print([res[i] for i in range(10)])
    ```

3. Python

    由于 `c_void_p` 是一个不确定类型的指针，因此我们再调用的时候应该避免直接这么用，可以用一个工厂函数来创建不同类的的 GoSlice。

    其实不写也无所谓，谁会看到这里呢？

    ```python
    import array
    from typing import Type
    from ctypes import (POINTER, cdll, c_longlong, Structure, _SimpleCData, pointer)
    GoSliceTypes = dict()
    def GoSlice(cType: Type[_SimpleCData]) -> Type[Structure]:
        """GoSlice 工厂函数，返回的是不同类型的 GoSlice"""
        t = GoSliceTypes.get(cType)
        if t:
            return t
        t = type(
            "GoSlice",
            (Structure, ),
            dict(_fields_=[
                ("data", POINTER(cType)),
                ("len", c_longlong),
                ("cap", c_longlong),
            ]),
        )
        GoSliceTypes[cType] = t
        return t

    __library = cdll.LoadLibrary('library.so')
    
    GoIntSlice = GoSlice(c_longlong) # 创建 []int 类型的 Slice
    
    return_int_slice = __library.returnIntSlice
    return_int_slice.argtypes = [GoIntSlice, POINTER(GoIntSlice)]
    return_int_slice.restype = POINTER(c_longlong)
    
    arr1 = (c_longlong * 10).from_buffer(array.array("q", range(10, 0, -1))) # 创建参数，c_types 的数组能够传给一个指针变量，指向这个数组的第一个元素
    slice_1 = GoIntSlice(
        data=arr1,
        len=10,
        cap=10,
    )
    
    arr2 = (c_longlong * 10).from_buffer(array.array("q", range(10, 0, -1)))
    
    # pointer 类型
    slice_pointer = pointer(GoIntSlice(
        data=arr2,
        len=10,
        cap=10,
    ), )
    
    res = return_int_slice(slice_1, slice_pointer)
    print(list(arr1))
    print(list(arr2)) # 打印两个array，发现都被 Go 修改了去
    
    print([res[i] for i in range(10)]) # 虽然我这边返回 0 - 9，不过实际上打印出来的最后一位是 1374389923320 
    ```

## 7.1 Slice 的扩容

我上面讲传 Slice 对象和 Slice 的指针是一样的，其实是不准确的，如果 Go 的 Slice 发生了扩容，那情况又不一样了，我们拿 ctypes 来举个例子

先编写一定会触发扩容的代码

```go
//export expandSlice
func expandSlice(slice []int, slicePoint *[]int) {
	res := make([]int, 10, 10) // # 3
	for idx, _ := range res {
		res[idx] = idx
	}
	slice = append(slice, res...)
	*slicePoint = append(*slicePoint, res...)
}
```

```python
__library = cdll.LoadLibrary('library.so')

GoIntSlice = GoSlice(c_longlong)

expand_slice = __library.expandSlice
expand_slice.argtypes = [GoIntSlice, POINTER(GoIntSlice)]

arr1 = (c_longlong * 10).from_buffer(array.array("q", range(10, 0, -1)))
slice_1 = GoIntSlice(
    data=arr1,
    len=10,
    cap=10,
)

arr2 = (c_longlong * 10).from_buffer(array.array("q", range(10, 0, -1)))
slice_pointer = pointer(GoIntSlice(
    data=arr2,
    len=10,
    cap=10,
), )

expand_slice(slice_1, slice_pointer)
print(slice_1.data, slice_1.len, slice_1.cap) # 1
print(slice_pointer.contents.data, slice_pointer.contents.len, slice_pointer.contents.cap) # 2
print([slice_pointer.contents.data[i] for i in range(slice_pointer.contents.len)]) # 3
```

1. Slice 1 的数据完全没变, cap 和 len 都是 10

2. slice_pointer 里面的 cap 和 len 都翻倍了

3. 使用 len 重新构建新的数组

所以，还要什么自行车，别吧 Slice 和 array 当做返回参数了，多麻烦，直接传入一个 Slice 的指针，让 Go 自己去扩容吧。

> 这种方法理论上是没问题的，因为参数 `slicePoint *[]int` 这个指针是 C 传过来的，Go 并不会进行 GC，让然也包括 Slice 里面的其他数据，Go 都不会去 GC
>
> 这纯粹是我的猜测，没有经过校验

> 需要特别注意的是，cap 这个值千万不要乱写，就和 len 保持一直，和实际的列表长度一样。
>
> 在 Go 中，cap 是表示 Slice 的可用空间的，len 表示当前的 Slice 长度，如果你 cap 写的比 len 大，那 Go 就会认为这个 Slice 不需要扩容，可能会把其他内存里面的变量给改了，segment fault 警告。
>
> 不过这也是我的猜想，也没有经过验证

# 8. chan

TODO，虽然是 TODO 但是我感觉最好还是不要在其他地方用 Go 的 `chan` ，以后可能也不会补充这块的内容。

# 9. interface

TODO，虽然是 TODO 但是我感觉最好还是不要在其他地方用 Go 的 `interface{}` ，以后可能也不会补充这块的内容。

# 10. 多返回值

```go
//export multiReturn
func multiReturn() (int, int) {
	return 1, 2
}
```

C 原生不支持多返回值，因此再看 `library.h` 文件，会发现此时多了一行定义

```c
/* Return type for multiReturn */
struct multiReturn_return {
	GoInt r0;
	GoInt r1;
};
extern struct multiReturn_return multiReturn();
```

那就懂了啊，不就是[结构体作为返回值](#52-结构体作为返回值)吗。

我们还是拿 ctypes 举例吧，Cython 太啰嗦了，其实就是在做之前的事情。

```python
__library = cdll.LoadLibrary('library.so')

GoInt = c_longlong
class multiReturn_return(Structure):
    _fields_ = [
        ("r0", GoInt),
        ("r1", GoInt),
    ]
    
multiReturn = __library.multiReturn
multiReturn.restype = multiReturn_return

res = multiReturn()
print(res.r0)
print(res.r1)
```

# 11. 内存安全

这点实在太重要了，如果你还没看过这一章节，那我建议你还是不要在长期运行的服务中去调用 Go 的函数了（或者 C 的函数），一定会造成内存泄露的。

在 [指针](#63-问题) 这一小节，遇到了一些奇怪的问题，这些我猜测是由 Go 的 GC 造成的。

而在 [数组](#62-数组指针) 这一小节，我们甚至使用了 `C.malloc()` 来申请一片动态内存（或者说是 heap memory），这就让我要考虑内存泄露的问题，毕竟 Python 和 Go 都能够自动去 GC，而如果是在 `C.malloc()` 中申请的动态内存，又由谁来回收呢？

我写了和小程序来验证这个猜想，这里借助了 Python 的内存分析模块 `memory_profiler`。

简单来说，就是在循环中去调用 Go 函数，这个函数返回一个 `C.char`，下面是循环调用后的内存增长情况：

```txt
Line #    Mem usage    Increment  Occurrences   Line Contents
=============================================================
    54     47.9 MiB     47.9 MiB           1   @profile
    55                                         def main():
    56     67.5 MiB      0.1 MiB      300001       for _ in range(300_000):
    57     67.5 MiB     19.6 MiB      300000           a = hello(c_char_p(str(uuid.uuid4()).encode()))  # 循环去调用 go 程序 hello
    58                                         
    59     67.5 MiB      0.0 MiB           1       import gc
    60     67.5 MiB      0.0 MiB           1       gc.collect()  # GC 无法回收内存
```

所以要手动释放这部分内存，有两种方式。

## 11.1 在 Go 中释放内存

在 Go 中释放内存和申请内存一样，只需要调用 `C.free` 即可

```go
package main

/* 
// 记得要 include stdlib
#include <stdlib.h>
*/
import "C"

//export hello
func hello(a *C.char) *C.char {
    // 不能 free a 这个地址，因为这个 a 是由 Python 创建的，在栈内存上的变量，无法被回收
	var str string = C.GoString(a)
	return C.CString(fmt.Sprintf("hello %s\n", str))
}

//export freeChar
func freeChar(addr *C.char) {
	C.free(unsafe.Pointer(addr))
}
```

重新编写 Python 程序

```python
from memory_profiler import profile

import uuid
from ctypes import c_char_p, cdll, POINTER, c_char

__library = cdll.LoadLibrary('library.so')
hello = __library.hello
free = __library.freeChar

hello.restype = POINTER(c_char)


@profile
def main():
    for _ in range(300_000):
        a = hello(c_char_p(str(uuid.uuid4()).encode()))  # 循环去调用 go 程序 hello
        free(a)

    import gc
    gc.collect()  # GC 无法回收内存


if __name__ == "__main__":
    main()
```

结果

```txt
Line #    Mem usage    Increment  Occurrences   Line Contents
=============================================================
    13     47.5 MiB     47.5 MiB           1   @profile
    14                                         def main():
    15     54.3 MiB      0.2 MiB      300001       for _ in range(300_000):
    16     54.3 MiB      6.2 MiB      300000           a = hello(c_char_p(str(uuid.uuid4()).encode()))  # 循环去调用 go 程序 hello
    17     54.3 MiB      0.3 MiB      300000           free(a)
    18                                         
    19     54.3 MiB      0.0 MiB           1       import gc
    20     54.3 MiB      0.0 MiB           1       gc.collect()  # GC 无法回收内存
```

可以看到内存确实减少，不过为什么还是多了 6.2 MiB 的内存呢？这个我也确实没琢磨明白。

由于 Python 是调用方，所以在参数方面，相对安全，因为变量指针都是由 Python 保存的，参与 Python 的 GC。

**在 Go 函数中的变量，无论是存在堆内存还是栈内存（反正都是由 Go 自己控制），都会参与到 Go 的 GC 中。但一旦涉及到返回值，由于 Cgo 的处理，会在堆内存上创建一些变量，且 Go 不会管理这些指针，因此必须回收。**

> 其实 [Go 官方博客](https://go.dev/blog/cgo) 已经说了，C.CString 是必须要 free 的。

## 11.2 在 Cython 中释放内存

Cython 中的 API 也能回收内存，我们拿数组举例：

```go
//export returnIntArray
func returnIntArray(first *int, length int) uintptr {
    // 不重复写了，可以去上面在看下
}
```

cython 中这么写。

```cython
from libc.stdlib cimport malloc, free

def go_return_int_array(youArray: List[int]):
    cdef GoInt[:] carray = array.array("q", youArray)
    cdef GoInt *carray_p = &carray[0]
    cdef GoUintptr res_addr = returnIntArray(carray_p, len(youArray))
    cdef GoInt *res = <GoInt*> res_addr # 返回的结果，先转化成一个指针
    print(carray.base) # 这里是 memoryview 对象，我们可以直接获取他内部的对象
    print([res[i] for i in range(10)]) # 打印返回的结果，我们操作指针移动 10 次，去取值
    free(res)
```

其实 Cython 在内存回收上也做了一些花样，可以查看 [Cython文档](https://cython.readthedocs.io/en/latest/src/tutorial/memory_allocation.html)

# 12. 总结

经过这一波折腾，我算是对 Python 调用 C，Go 调用 C 有了一波船新的认识。

实际上，Python 和 Go 也不能直接对话，还是要借助 C 这个翻译大师。

Cgo 之于 Go，就如 Cython 之于 Python。

如果没什么必要，我觉得真的直接用 Cython 或者 C 去编写就行，用 Go 真的就是，没必要，对于实在想用 Go 的人，我建议还是用微服务（RPC或者HTTP）的形式去调用吧，真心话！

其实我在工作的时候没这么多复杂的场景，也就是字符串来回，但我还是去探索了 Python 和 Go 不同的组合技，后面发现这里面其实还是水挺深的，一脚蹚下去差点给我淹死。不过我也确实学了很多 Cgo 的知识、Cython的知识和 C 的知识，也对指针有了新的认识。

所以我也是现学现卖，文中的不足还请各位指正。

最后，希望能这篇文章能帮助到 *不小心* 走到这条路上的人。

# 13. 参考

- [https://github.com/fluhus/snopher](https://fluhus.github.io/snopher/)

- https://stackoverflow.com/questions/65572429/how-to-return-go-array-slice-ist-to-a-c-function

- ...(此处省略一万个 stackoverflow )

# 14. 转载说明

欢迎转载，转载请备注作者的 GitHub 主页：https://github.com/ZinkLu
