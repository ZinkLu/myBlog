---
title: "【HomeServer】- 平台搭建"
date: "2022-12-31T12:41:00+08:00"
draft: false
summary: 【别硬折腾】系列之 【HomeServer. Part2.】
isMath: false
---

> 【别硬折腾】是我折腾硬件一些记录。
> 
> 这是我的第一期的内容，家庭服务器。
> 
> 本期分为三个篇章：
> 
> Part1 记录了家庭网络环境、设备的一些演变；
> 
> Part2 以我最新的方案为例，记录搭建的全过程；
> 
> Part3 是应用部分，我现在正在使用家庭服务器做的一些事情；
> 
> 本篇为Part2，介绍搭建 proxmox 虚拟化管理平台，并且使用不同虚拟机来管理不同的资源。

# 1. 目标

1. 在工业小主机上搭建虚拟化平台；
2. 使用虚拟机管理家中的硬件资源，如电源、宽带、存储等；
3. 能够安装一些应用，来管理数据，如电影、文档、照片、智能家电等。

# 2. 虚拟机平台系统选择

在 Linux 下，KVM 是合适的虚拟化解决方案。我之前选择的是使用 Ubuntu22.04 作为虚拟机的管理平台的，Ubuntu 这种发行版中也有 libvirt 作为虚拟机实现的上层接口，也有 cockpit 这种基于 web 的管理工具。

可惜我在用使用 Ubuntu 作为宿主机系统的时候还是遇到了各种各样的问题，在好一顿折腾后都没有解决。最后不得不切换到了  Proxmox Virtual Environment（简称 PVE），一款基于 debian 的虚拟机管理工具。它是直接基于 KVM（QEMU）进行的封装，不再依赖 libvirt，同时也可以管理 lxc 。

## 2.1 Ubuntu 有什么问题？

Ubuntu22.04 的是基于 5.15 内核的，似乎无法完美驱动我这台小主机的 N5105 的 12 代 CPU 和 i226v 网卡，在运行虚拟机时总会出现虚拟机的不间断重启，最直接的影响就是会导致网络突然中断。

后面我又把 Ubuntu 的内核升级到了 5.17 、5.19 和 6.0 ，调整过一些 BIOS 和虚拟机的参数，但最终结局都是虚拟机运行一段时间后的随机重启或死机，也尝试过把 Ubuntu 升级到 22.10(kernel 5.19)，最终也是徒劳无功。

> 并且这些内核对于虚拟机的 PCI 直通支持都有问题，有些可以直通网卡但无法直通显卡，有些直通了显卡但驱动有问题，有些干脆都不支持直通。 
> 
> PCI 直通虽然不是硬性需求，但如果我们希望搭建音影服务的话必须用到核显的硬件编解码功能，否则孱弱的 N5105 根本支持不起高清电影播放。

我还曾经在 Docker 中安装了 OpenWRT，这意味着直接使用宿主机来进行了网络管理，但不幸的是在 OpenWRT 中出现了许多的内核错误，也只能放弃。

> 哦对了，我后面还安装了 virtualbox 来尝试托管 OpenWRT，同样也是老是死机。只能说这个小主机的硬件肯定确实比较新。

但我想，基于 cockpit + libvirt + kvm 的虚拟化平台肯定是没有任何问题的，甚至我认为这个就是 Home Server 最简单搭建也正好够用的平台。

# 3. 系统安装

## 3.1 安装 PVE

在官网 [下载](https://www.proxmox.com/en/downloads) 下载 Proxmox VE ISO Installer，以最新版本为准，并将 ISO 制作成启动盘，在 macos 下我用 [balena Etcher](https://www.balena.io/etcher?ref=etcher_footer)，简单方便。

{{< img src=balenaetcher.png size=50% lines=注意，此操作会抹去U盘内容 >}}

将 BIOS 中的启动项设置为U盘后即可安装。

> 在你的工业主机供应商的官网上确认下当前的机器的 BIOS 的版本是不是最新的，记得使用最新的 BIOS。

{{< img src=proxmox.jpg size=50% lines=开始安装 >}}

这一路没啥好说的，按照默认值即可，记得时区最好选上海，直到来到网络设置这个页面。

{{< img src=proxmox-network.jpg size=100% lines=在这停顿 >}}

网络的配置比较讲究，一共有这么几项：

1. 网卡:
   
   这里是一个下拉框，你的主机有几个网口这里应该就有显示几张网卡。我这里写的是什么ens18，是因为我这是在虚拟机里面安装 PVE 做演示的原因，一般来说应该是 enp0s1 或者 ens1 之类的，并且数字是顺序递增的。
   
   这个选项理论上是随意选择的，但是选定了这样张网卡后，后续所有虚拟机的桥接网络都会走这张网卡，这张网卡也无法再被直通到其他虚拟机内。（直通意味着硬件对宿主机不可见）

   因此我建议选择第一个或者最后一个，由于网卡编号的顺序是和物理网口的排列顺序相关的，这样就很容易确定所对应的网口（机器上最左或者最后），确定了以后，这个网口可以做一个标记，可以空着或者插一些平时不常用的设备，因为所有的虚拟机都会使用这个接口发送数据，因此它的性能是会在一定程度上受损的。

2. 本地域名:
    
    可以随意一些，比如 `node1.big-house` 之类的。

3. IP
   
    由于此时软路由系统还没有安装，而这里的 IP 必须和未来的软路由 IP 处于同一个网段，即这里的 `192.168.31.25/24`，这样以后软路由也要成 `192.168.31.X/24` 的网段。

4. 网关
   
   填写未来主路由的地址，我这里将软路由设置为 `192.168.31.1`。

5. DNS

    可以写阿里云（233.5.5.5）或者电信（114.114.114.114）的DNS服务，也可以直接写网关的地址。

等待安装结束并重启。

{{< img src=proxmox-install.jpg size=50% lines=安装中 >}}

重启后，显示一个命令行，并提示你现在可以通过 web 来登录 PVE 的管理页面了。

{{< img src=commandline.jpg size=50% lines=提示 >}}

将电脑接上网线，然后在电脑上手动设置 IP 地址，也设定在和 `192.168.31.0/24` 这个网段，比如 `192.168.31.24/24`，并将网线另一端插到刚才设置的网卡对应的网口上（如果你是选择的第一个或者最后一个，试试最左或者最右的网口）。

> /24 代表着子网掩码为 255.255.255.0。

然后我们打开 `https://192.168.31.25:8006` 应该就能访问 PVE 的管理页面了。

如果浏览器提示链接不安全记得点击继续前往

{{< img src=chrome_warning.jpg size=50% lines=由于proxmox强制使用https，可能会被告知不安全 >}}

然后按照安装时输入的密码进行登录即可

{{< img src=proxmox-login.jpg size=50% lines=忘记密码的重装吧 >}}

出现这个界面就完成了，

{{< img src=proxmox-index.jpg size=100% lines=安装成功 >}}

## 3.2 安装虚拟机

在 PVE 安装完成后，他会自动将硬盘分为 local 和 local-lvm 两个分区（不考虑在引入外部存储或者 ceph），前者用来放一些 lxc-template 或者虚拟机的安装文件（如 ISO 镜像），后者则是用来放虚拟机的磁盘持久化文件的。

要安装一个虚拟机，我们需要先下载系统的安装文件，然后把他上传到 local 分区中的 ISO 镜像中。

{{< img src=vm-upload.jpg size=100% lines=上传镜像 >}}

接着点击右上角的 `创建虚拟机` 就可以可以创建了

{{< img src=vm-install.jpg size=100% lines=创建虚拟机 >}}

在后续的安装选项中，我们可以在 `操作系统` 选项卡中找到我们上传的 ISO 镜像

{{< img src=vm-image-choice.jpg size=100% lines=选择镜像 >}}

其他的选项我们将在后续章节做详细分享，这里我们先做基本了解。

下面两个步骤都需要网络才能进行，由于现在小主机还不能上网，先参考[网络](#5-网络)一节来安装一个主路由来让宿主机连入互联网。

## 3.3 替换源，启用企业源

我们需要将 PVE 原来的源替换为国内源，且要启用 PVE 的企业源。

我们需要先进入主机的 shell 界面，你可以直接通过 `ssh root@192.168.31.25` 来进行链接，也可以在管理页面上直接访问某一个宿主机节点的 shell，如下

{{< img src=proxmox-webshell.jpg size=100% lines=进入shell >}}

随后我们将 apt 源换成清华源

```bash
cp /etc/apt/sources.list /etc/apt/sources.list.bak
cat <<EOF > /etc/apt/sources.list
deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bullseye main contrib non-free
deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bullseye-updates main contrib non-free
deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bullseye-backports main contrib non-free
deb https://mirrors.tuna.tsinghua.edu.cn/debian-security bullseye-security main contrib non-free
EOF

cat <<EOF > /etc/apt/sources.list.d/pve-enterprise.list
# deb https://enterprise.proxmox.com/debian/pve bullseye pve-enterprise
deb https://mirrors.tuna.tsinghua.edu.cn/proxmox/debian bullseye pve-no-subscription
EOF
```

执行更新命令

```bash
apt update && apt upgrade
```

## 3.4 更新内核

先查看下 PVE 的内核版本，如果大于等于 6.1 就不用更新了

```bash
uname -r
```

```bash
# output
5.15.74-1-pve
```

由于彼时最新版本的 PVE 7.3 版本默认使用的是 5.15 的内核，还是有一些硬件驱动的问题，因此我们先安装 6.1 的内核。

```bash
apt install pve-kernel-6.1
```

安装完后记得重启一下小主机，这样，我们的虚拟机平台就算是搞定了。

# 4. 电源

如果你有一个 UPS 电源，我们就可以将电源当做一种资源管理起来。

电源是优先一种网络、存储等其他资源存在的资源，因此对它的管理只能在宿主机上进行，只有这样宿主机才有可能通知其他系统关机或者自己执行关机等操作。

可惜 PVE 现在还没有图形化的操作方法，这里可以参考[这篇文章]({{< ref "/content/posts/technical/设置NUT(Network UPS Tools)/index.md" >}})进行 UPS 电源的配置。

# 未完待续

# 5. 网络

# 6. 磁盘

# 7. 应用
