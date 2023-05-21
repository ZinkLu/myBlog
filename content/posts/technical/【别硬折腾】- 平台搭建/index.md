---
title: "【HomeServer】- 平台、网络搭建"
date: "2022-12-31T12:41:00+08:00"
draft: false
summary: 【别硬折腾】系列之 【HomeServer. Part2.】安装 PVE 虚拟机系统，安装 ikuai 虚拟机并直通网卡，安装 OpenWrt 虚拟机来管理网络。
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
> 本篇为Part2，介绍搭建 proxmox 虚拟化管理平台，并且使用不同虚拟机来管理不同的资源。由于篇幅过长，本篇只会讲虚拟平台和网络。

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

{{< img src=balenaetcher.png size=100% lines=注意，此操作会抹去U盘内容 >}}

将 BIOS 中的启动项设置为U盘后即可安装。

> 在你的工业主机供应商的官网上确认下当前的机器的 BIOS 的版本是不是最新的，记得使用最新的 BIOS。

{{< img src=proxmox.jpg size=50% lines=开始安装 >}}

这一路没啥好说的，按照默认值即可，记得时区最好选上海，直到来到网络设置这个页面。

<span id="PVE网络设置"></span>

{{< img src=proxmox-network.jpg size=100% lines=在这停顿 >}}

网络的配置比较讲究，一共有这么几项：

1. 网卡:
   
   这里是一个下拉框，你的主机有几个网口这里应该就有显示几张网卡。我这里写的是什么ens18，是因为我这是在虚拟机里面安装 PVE 做演示的原因，一般来说应该是 enp2s0 或者 ens0 之类的，并且数字是顺序递增的。
   
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

{{< img src=proxmox-install.jpg size=100% lines=安装中 >}}

重启后，显示一个命令行，并提示你现在可以通过 web 来登录 PVE 的管理页面了。

{{< img src=commandline.jpg size=100% lines=提示 >}}

将电脑接上网线，然后在电脑上手动设置 IP 地址，也设定在 `192.168.31.0/24` 这个网段，比如 `192.168.31.24/24`，并将网线另一端插到刚才设置的网卡对应的网口上（如果你在安装时选择的第一个或者最后一个网卡选项，试试最左或者最右的网口）。

> /24 代表着子网掩码为 255.255.255.0。

然后我们打开 `https://192.168.31.25:8006` 应该就能访问 PVE 的管理页面了。

如果此时浏览器提示链接不安全记得点击继续前往

{{< img src=chrome_warning.jpg size=50% lines=由于proxmox强制使用https，可能会被告知不安全 >}}

然后按照安装时输入的密码进行登录即可

{{< img src=proxmox-login.jpg size=50% lines=忘记密码的重装吧 >}}

出现这个界面就完成了。

{{< img src=proxmox-index.jpg size=100% lines=安装成功 >}}

## 3.2 安装虚拟机

在 PVE 安装完成后，他会自动将硬盘分为 local 和 local-lvm 两个分区（不考虑引入外部存储或者 ceph），前者用来放一些 lxc-template 或者虚拟机系统镜像，后者则是用来放虚拟机的磁盘文件的。

要安装一个虚拟机，我们需要先下载系统的安装文件，然后把他上传到 local 分区中的 ISO 镜像中。

{{< img src=vm-upload.jpg size=100% lines=上传镜像 >}}

接着点击右上角的 `创建虚拟机` 就可以可以创建了

{{< img src=vm-install.jpg size=100% lines=创建虚拟机 >}}

在后续的安装选项中，我们可以在 `操作系统` 选项卡中找到我们上传的 ISO 镜像

{{< img src=vm-image-choice.jpg size=100% lines=选择镜像 >}}

其他的选项我们将在后续章节做详细分享，这里我们先做基本了解。

接下来，我们需要更新软件并且安装最近的内核。由于下面两个步骤都需要网络才能进行，而现在小主机还不能上网，可以先参考[网络](#5-网络)一节来安装路由系统以提供网络服务。

## 3.3 替换软件源+启用企业源

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

# 5. 网络

在上篇中，我们规划安装一个 ikuai 作为主路由系统来完成转发、拨号等工作以提供互联网服务，安装 OpenWRT 作为旁路由系统以提供额外的增强服务。让我们先来安装 ikuai 主路由。

> 实际上，我们可以只安装 OpenWRT 作为我们的软路由系统，但我总感觉 OpenWRT 更新的太快，有的时候不是很稳定，还是将这两者分开更加好一些，至少在 OpenWRT 不稳定的时候不至于影响互联网的访问。

## 5.1 网络硬件分配

我的小主机是 4 个网口的，所以我对这几个网口是这么安排的：

1. 由于宿主机的网卡无法被直通到虚拟机内部，桥接一张网卡到 ikuai 中；
2. 其他三张网卡全部直通 ikuai；

{{< img src=网络拓扑图-网络.png size=100% lines=网络拓扑 >}}

网卡直通(pci passthrough)将光猫、PC、WIFI链接在了一起，而桥接(linux bridge)又把它们和所有其他虚拟机链接在了一起。这就组成了一个大的局域网。

## 5.2 安装 ikuai

### 5.2.1 下载并上传 ISO 文件

1. 下载 [ISO 文件](https://www.ikuai8.com/component/download)，推荐 64 位的；
2. 按照[这里的步骤](#32-安装虚拟机)上传 IOS 镜像并开始安装虚拟机；
3. 确保《操作系统》中的《ISO镜像》是刚才下载的 ikuai 系统，其他保持默认，一直到《磁盘》这一个选项中。

### 5.2.2 配置硬盘、CPU和内存

对于硬盘，我们将《总线/设备》改成 SATA，同时，将磁盘大小改成 1G（大点也没事）。

{{< img src=image-20230218142314191.png size=100% lines=设置硬盘 >}}

将 CPU 核心数量调到 2，同时，为了达到最佳的性能，我们将CPU的类别调到 host（推荐所有的CPU类型都是host，除非你考虑后期迁移虚拟机）。

{{< img src=image-20230218142735788.png size=100% lines=设置CPU >}}

内存设置为 2048 MiB 这是 64 位 ikuai 所需要的最小内存数量。

{{< img src=image-20230218143026139.png size=100% lines=设置内存 >}}

### 5.2.3 网络和网卡配置

按照我们在 [5.1](#51-网络硬件分配) 小节中的计划，我们应该先建立一个到 **桥接网络** 宿主机，因此我们需要在《网络》选项卡中添加一个桥接设备，如下图：

{{< img src=image-20230218143225873.png size=100% lines=配置桥接网络 >}}

然后直接最后一步，点击确认。（注意最后一步中左下角的 `创建后启动` 可以先去掉）

接着，我们需要配置网卡的直通，如下图所示，先找到我们刚刚创建的虚拟机，在《硬件》中添加一个《PCI设备》

{{< img src=image-20230218144012929.png size=100% lines=修改虚拟机硬件 >}}

但跳出来的选项可能不是特别的友好，比如下图

{{< img src=image-20230218144127703.png size=100% lines=PCI选项 >}}

我们可以通过宿主机的终端运行`lspci`并找到 `Ethernet controller` ，记下他们对应的编号。

{{< img src=image-20230218144342282.png size=100% lines=找到网卡的PCI >}}

然后找到对应的编号即可

{{< img src=image-20230218144543050.png size=100% lines=编号对应网卡 >}}

我们只能直通另外 3 张网卡，所以我们需要确定现在宿主机使用的网卡是哪一张。继续通过终端输入 `ip -o link show | grep vmbr0`：

{{< img src=image-20230218145332763.png size=100% lines=找到虚拟机使用的网卡 >}}

得到一个 enp 开头（当然你的可能是别的开头的）的就是当前宿主机正在使用的真正的物理网卡了，它的编号和 PCI 的编号是对应的，因此在我上面给到的例子中，除了 `0000:05:00.0` 之外的其他网络 PCI 设备，全部都选中，直通到虚拟机中。

最终我们可以在虚拟机的《硬件》面板中看到这些设备：

<span id="桥接MAC"></span>
{{< img src=image-20230218145641490.png size=100% lines=PCI直通的硬件 >}}

加上我们刚才桥接的一张虚拟网卡后，整个网络就被配置成了我们[想要的样子](#51-网络硬件分配)。

### 5.2.4 启动并设置IP地址

{{< img src=image-20230218151654637.png size=100% lines=启动开关在右上角 >}}

点击右上角的启动，然后进入《控制台》进行进一步的操作。

实际上，ikuai 此时并没有安装完成，我们需要将ikuai先安装在刚才分配的 1G 的磁盘中，按照提示输入 1 后回车。

{{< img src=image-20230218154509545.png size=100% lines=选择硬盘 >}}

等待安装完成后会自动重启，此时我们才能看到 ikaui 的真正的设置界面：

{{< img src=image-20230218154633777.png size=100% lines=后端设置界面 >}}

我们先设置 LAN 的地址以便后续是用 WEB 界面在浏览器中进行进一步的操作。

> 注意，我们应该将 LAN 设置为我们桥接进去的网卡，如果此时 LAN 对应的不是桥接的网卡，必须使用 《1. 设置网卡绑定》来将桥接的网卡指定为 LAN。
>
> 分辨桥接的网卡很简单，你可以在 [《硬件》面板](#桥接MAC) 里面找到他的 MAC 地址。

先选择 2，再选 0，输入地址。由于我们刚才都是在 `192.168.31.0/24` 这个网段的，这里我们也一样要保持这个网段不变，这里可以设置为 `192.168.31.1/255.255.255.0`，这就是我们局域网内的网关地址了。

{{< img src=image-20230218160704723.png size=100% lines=设置LAN地址 >}}

> 我们再安装 PVE 的时候曾经手动设置过[网络](#PVE网络设置)，那么这里的 LAN 地址可以设置成 PVE 的网关地址。

### 5.2.5 设置 WAN

刚才在 PVE 中，我们设置了最左或者最右的一张网口作为管理网卡（在我的示例中是 enp5s0），此时我们将光猫和另外边的网口用网线连到一起。

打开浏览器，输入 `http://192.168.31.1` 就能够打开 ikuai 的 web 管理界面了。（默认密码 admin/admin）

选择 《网络设置》《内外网设置》《wan1》

{{< img src=image-20230218162506004.png size=100% lines=设置WAN >}}

这里我们要选择刚才和光猫连在一起的网卡，网卡的顺序是不会变的，应该不是 eth1 就是 eht3 才对（如果和我一样，eth0 应该是桥接网卡）

{{< img src=image-20230218163243965.png size=100% lines=绑定网卡 >}}

然后我们选择上网模式，如果你是用光猫拨号的，这里选择 DHCP 即可。在这里我是自己拨号的，因此选择 ADSL/PPPoe拨号。

> 如果是 DHCP 的话直接确定就行了，其他的都别改了。
>
> 如果是拨号的话，输入用户名密码后进行连接测试即可。

{{< img src=image-20230218163243965_副本.jpeg size=100% lines=选择正确的上网方式 >}}

设置完了以后，拖到最下面按保存。

### 5.2.6 设置 LAN

我们进入《网络设置》《内外网设置》《lan1》

进入 lan 后，我们打开《高级设置》在《LAN拓展模式》里面选择《链路桥接》，然后把其他的都勾上。

{{< img src=image-20230218170428192.png size=100% lines=设置br-lan >}}

至此主路由的部分就算是设置完毕了，如果拨号成功，一切正常的话，宿主机应该就可以上网了。

> 我之前也碰到过无法上网的情况，在宿主机中根本ping不通虚拟机，这时候不妨重启一下软路由，可能 Linux 桥接的问题。

## 5.3 安装 OpenWRT

在我的网络体系中，ikuai 是用来拨号链接互联网的，OpenWRT 则提供了网络插件，如 frp、transmission等。

### 5.3.1 下载 OpenWRT 镜像并上传

到官网的[下载页面](https://downloads.openwrt.org/releases)找到所需的版本，对我来说，我需要的是最新的 x86/64 版本的安装文件，所以我应该这么选:

```text
https://downloads.openwrt.org/releases/{latest_version}/targets/x86/64/
```

选择 squashfs + combined 不带 efi 的版本进行下载：`generic-squashfs-combined.img.gz`

解压，获取 img 文件

```bash
gzip -d generic-squashfs-combined.img.gz
```

### 5.3.2 创建虚拟机

在创建虚拟机时，需要记住 VM ID，后面需要用到，下一步

{{< img src=1684643255551.jpg size=100% lines=常规 >}}

在操作系统选项卡中，先选择不使用任何介质，kernel 选择 5.x 或者 6.x，下一步

{{< img src=1684643482462.jpg size=100% lines=操作系统 >}}

系统选项默认，下一步

在磁盘这里，我们删除默认分配的磁盘，下一步

{{< img src=1684644905100.jpg size=100% lines=设置硬盘 >}}

CPU 仍然 HOST 模式，核心的话可以给 1个，下一步

{{< img src=image-20230218142735788.png size=100% lines=设置CPU >}}

内存的话 1024MiB 绰绰有余，下一步

网络默认走桥接，看下配置是否和下图一致，下一步，完成创建。

{{< img src=1684643938550.jpg size=100% lines=设置网络 >}}

### 5.3.3 导入镜像

我们需要先进入 web shell

{{< img src=proxmox-webshell.jpg size=100% lines=进入shell >}}

然后输入命令来导入刚才的镜像文件

```bash
qm importdisk ${VM_ID} /var/lib/vz/template/iso/${OPENWRT_IMG} local-lvm
```

其中，`${VM_ID}` 代表刚才创建的虚拟机的 ID，`${OPENWRT_IMG}` 表示上传的镜像的名称。

{{< img src=1684645070862.jpg size=100% lines=导入成功 >}}

导入成功后，应该就可以在虚拟的管理页面看到这块磁盘了

{{< img src=1684645152989.jpg size=100% lines=未使用的磁盘 >}}

我们需要将这块硬盘启用。双击这块硬盘，将总线/设备改为 SATA 后添加

{{< img src=1684645232607.jpg size=100% lines=添加磁盘 >}}

随后，打开虚拟机选线中的引导顺序一栏，将这块硬盘的引导顺序改成第一。

{{< img src=1684645330553.jpg size=100% lines=双击引导顺序选项卡 >}}

{{< img src=1684645403179.jpg size=100% lines=启用磁盘作为引导并修改顺序 >}}

完成，开机！

### 5.3.4 设置 OpenWRT

进入控制台后，使用命令行编辑 OpenWRT 的配置

```bash
vi /etc/config/network
```

配置其 ip 地址，网关和 DNS 服务器

```conf
config interface 'loopback'
	option device 'lo'
	option proto 'static'
	option ipaddr '127.0.0.1'
	option netmask '255.0.0.0'

config globals 'globals'
	option ula_prefix 'fd93:1518:d4a5::/48'

config device
	option name 'br-lan'
	option type 'bridge'
	list ports 'eth0'

config interface 'lan'
	option device 'br-lan'
	option proto 'static'
	option ipaddr '192.168.31.189' # 给定固定的IP地址，要属于 192.168.31.x的网段
	option gateway '192.168.31.1' # 默认网关为 ikuai
	option netmask '255.255.255.0'
	option ip6assign '60'
	list dns 192.168.31.1 # DNS 可以和默认网关一致
```

配置完成后，重启 OpenWRT 的网络

```bash
/etc/init.d/network restart
```

重启完毕后，如果能 ping 通 baidu.com 则说明没问题，此时打开浏览器，输入 `192.168.31.189` 便可以打开 OpenWRT 的 web 界面。

最后，别忘记修改 OpenWRT 的密码。

大功告成。

# 6. 未完待续

本篇分享到这里先告一段落，没想到光平台和网络就已经这么长了，后面我会将存储（组件硬盘阵列）单独拿出来进行分享。
