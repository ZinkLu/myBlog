---
title: "【HomeServer】- 存储平台搭建"
date: "2023-05-21T16:08:00+08:00"
draft: false
summary: 【别硬折腾】系列之 【HomeServer. Part2.】后续，使用 mdadm 搭建软 raid 并使用 openmediavault 进行硬盘的管理
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
> 距离上一次的分享已经过了很长时间，近半年一直在写文档的样子，所以博客就不太想写，本篇为Part2 的后续，介绍了使用 PVE 虚拟机管理存储资源。

# 1. 前言

为什么要将存储的部分额外分一章来写。

一方面，上一章中平台 + 网络的内容已经十分的多，再写下去就有点太多了。

另一方面，相对于上一节中 PVE + iKuai + OpenWrt 这种大众方案来说，我的存储方案还是显得有点“离经叛道”了，考虑到数据的安全性，这里就完全不推荐，因此也将这部分分开。

虽然这个方案“离经叛道”，但架不住它便宜啊，因此如果你是有一些Linux基础，还是可以折腾一下的。本篇也会出现大量的命令行，系好安全带，准备出发了。

# 2. 平台介绍

既然都说了便宜，那就势必要先介绍一下我的平台了。

1. 我选择购入了一个铁威马的 `D2-310` 作为工业主机的 DAS，通过 USB3 和工业主机连接；
2. 在工业主机中组建软 Raid；
3. 安装 [openmediavault](https://www.openmediavault.org/) 虚拟机，设置 USB 直通到虚拟机。让 OMV 对阵列进行管理，同时提供 NAS 的能力（通过网络共享）。

`D2-310` DAS 价格比较便宜，只要 500 左右，买两块希捷的 8T 的企业盘，加在一起总共不超过 2700，这个价格刚好是一个群晖双盘位 NAS 的价格，相当于立省两块硬盘的钱。

注意！！！！！！

正是由于 DAS 是通过 USB3 进行链接的，它的**稳定性**和**传输速度**都十分的不理想。

传输速度还好，反正 USB3 的理论传输性能在 500M/s，我内网是前兆的，即使是 2.5G 的带宽也赶不上 USB 的传输速度。

稳定性就比较头疼了，虽然 DAS 和 NAS 一样，都是将硬盘通过 SATA 接口和主板直接相连，但 DAS 没有独立的 CPU，必须通过外部接口和其他主机相连，也正因为如此，DAS 在稳定性上还是差了一大截，我就常常遇到过掉盘的情况。这也是我不推荐这个方案的理由。

> DAS 是 Direct-attached storage 的简称。
> 
> DAS 设备的主板比较简单，没有真正的 CPU，只有用于管理、驱动硬盘的芯片，接口方面更是少的可怜，一般也是有个 USBA 或者 USBC 接口用来传输数据，你可将它看做是一个大号的硬盘盒。
> 
> 但 DAS 上的芯片支持硬 Raid，不过这里我还是选择软 Raid。软 Raid 的好处是，万一硬件坏了，硬盘拿出来还是可以恢复阵列。
> 
> 而 NAS 则是一个完整的 X86 或者 arm 的电脑（也可以看做工业主机），它提供了一个 PC 完整的接口与功能。

也正因为是 USB 的链接方式的不稳定，像 OMV 这种 NAS 系统是[不允许用户在 USB 设备上组建软 Raid 的](https://forum.openmediavault.org/index.php?thread/26727-usb-raid-1/)。不过好在如果是已经组好的 Raid，OMV 还是可以识别的，至少我们不用使用命令行维护、共享硬盘阵列了（逼急了直接命令行也行）。

因此，第一件事就是需要使用 mdadm 命令行工具在 DAS 的双硬盘上组组件软 Raid。

> 论坛的帖子上也说可以安装插件来解除 OVM 对 USB 的限制，更多的认为用 USB 组 raid 是用来教学的。建议各位就当看个热闹就行，如果这套设备出了什么大纰漏，我也会第一时间进行分享。

# 3. 组建软 raid

将 DAS 和小主机链接，以下的操作全部都可以在 PVE 里面操作。

1. 安装 mdadm

    ```bash
    apt install mdadm
    ```

2. 查看已经连接的硬盘

    ```bash
    fdisk -l
    ```

    此时应该成功显示两块硬盘，Disk model 就是铁威马

    ```bash
    Disk /dev/sdc: 7.28 TiB, 8001563222016 bytes, 15628053168 sectors
    Disk model: TerraMaster
    Units: sectors of 1 * 512 = 512 bytes
    Sector size (logical/physical): 512 bytes / 4096 bytes
    I/O size (minimum/optimal): 4096 bytes / 4096 byt

    Disk /dev/sdb: 7.28 TiB, 8001563222016 bytes, 15628053168 sectors
    Disk model: TerraMaster
    Units: sectors of 1 * 512 = 512 bytes
    Sector size (logical/physical): 512 bytes / 4096 bytes
    I/O size (minimum/optimal): 4096 bytes / 4096 bytes
    ```

3. 组件 Raid1（或者 Raid0 也行，随你）

    ```bash
    # --create 创建
    # --level=1 创建 Raid1
    # --raid-devices -n 使用到的设备数量
    # --spare-devices -x 备份盘数量
    # 
    mdadm --create  --verbose /dev/md0 --level=1 --raid-devices=2 /dev/sdb /dev/sdc

    # 等同于
    # sudo mdadm -C -v /dev/md0 -l1 -n2 /dev/sdb /dev/sdc
    ```

    让你输入回车后，Raid 就已经在后台进行初始化了，通过 `cat /proc/mdstat` 命令可以查看初始化的进度，如下


    ```bash
    #设备 ：状态    类型   设备1   设备2
    md0 : active raid1 sdc[1] sdb[0]
        7813894464 blocks super 1.2 [2/2] [UU]
        [=>...................]  resync =  7.1% (561358976/7813894464) finish=599.7min speed=201542K/sec
        bitmap: 55/59 pages [220KB], 65536KB chunk
    ```
    
    上面的进度大概是这么个意思：正在使用 sdc 和 sdb 两个设置创建 md0 的 raid1，进度为 7.1%。

    这个过程比较漫长，需要耐心等待。

    完成后，通过 mdadm 来查看阵列信息

    ```bash
    sudo mdadm --detail --scan

    # 应该会打印如下信息
    # ARRAY /dev/md0 metadata=1.2 name=XXXXX:0 UUID=xxxxxxxx:xxxxxxxx:xxxxxxxx:xxxxxxxx
    ```
    
4. 格式化 Raid

    等初始化结束后，就可以对阵列进行格式化并挂载了。

    这里我们将硬盘格式化成 xfs 格式

    ```bash
    mkfs.xfs -F /dev/md0
    ```

OK，到这里我们就已经完成了阵列的创建，并且成功的将它格式化成了 xfs 的格式。

紧接着我们可以通过 openmediavault 来对阵列进行管理、挂载和共享了。

# 4. 安装 openmediavault 并直通 USB

下载最近稳定版本的 [openmediavault ios镜像](https://www.openmediavault.org/download.html)。

安装步骤这里就不赘述了，可以参考上一篇中的[安装虚拟机]({{< ref "/content/posts/technical/【别硬折腾】- 平台搭建/index.md#32-安装虚拟机" >}})一节来创建 OMV 的虚拟机。

安装完成后，我们需要将铁威马 USB 设备直通到 OMV 中。

设置直通 USB

{{< img src=1684663282742.jpg size=100% lines=USB直通 >}}

{{< img src=1684663346278.jpg size=100% lines=注意选择通过USB供应商/设备ID进行直通 >}}

# 5. 设置 OMV 的挂载并共享

重新启动 OMV 后，可以在磁盘一栏中看到我们挂载的设备

{{< img src=1684663520567.jpg size=100% lines=磁盘管理中正常显示DAS中的设备 >}}

在软 raid 中看到组件好的 raid0 

{{< img src=1684663535993.jpg size=100% lines=软raid管理 >}}

随后，在 OMV 的文件系统菜单中，我们可以将 raid 挂载

{{< img src=1684668201566.jpg size=100% lines=创建挂载 >}}

最后，通过共享文件夹选项对磁盘进行共享

{{< img src=1684668213767.jpg size=100% lines=共享文件夹 >}}

> 这里的共享文件夹对于 OMV 的逻辑来说是**设置需要共享的文件夹**，只要再次添加的文件夹才能被后续的*服务*中共享。
>
> 同时，设置共享文件夹时还能设置子路径，十分方便。

之后，我们将这些被分享的文件夹通过网络服务（nfs/smb）暴露在网络上。

{{< img src=1684668221463.jpg size=100% lines=SMB共享 >}}

> SMB 的共享选项请酌情选择。

此时，在 Windows 和 Mac 上应该就能看到被分享的文件夹。

# 6. SMART

除了对文件进行分享外，OMV 还提供了可视化的 SMART 工具，能够对硬盘的状态进行监控。

{{< img src=1684668918634.jpg size=100% lines=SMART >}}

SMART 还能设置计划任务，对硬盘进行状态的扫描，这里就不展开说了。

# 7. 总结

对于像群辉这种品牌的 NAS，他们的硬件可能不算是出色，但这些 NAS 厂商的软件系统真的十分优秀，不是像我这种 USB 方案能比的，对于数据的保护可能会更好，数据无价，如果不缺钱或者不想折腾，还是建议买一个群辉来管理自己的数据。

储存是应用的基础，下一部分我会分享下我在工业主机上搭建的一些应用，这些应用也是所谓的 HomeServer 的核心，能够为日常家生活动提供一些便利。
