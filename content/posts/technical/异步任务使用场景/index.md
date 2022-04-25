---
title: "异步任务使用场景和注意事项"
date: "2022-04-25T11:24:00+08:00"
draft: false
description: 能不异步就不异步
summary: 
---

# 1. 前言

异步任务是Flask模板中集成的功能之一，可以通过celery完成分布式任务，他本质上是一个多进程系统，只不过以服务的形式拆分去取，解耦的同时也能做到动态扩缩worker数量。

不过正如所有的多进程一样，异步任务也存在调试困难的问题。特别是在异步任务中去同步状态，或者频繁读写。这类的操作轻则，重则数据库死锁。

因此还是那句话：

> ***引入异步任务会提升系统复杂度，并且会引入额外的工作量（比如任务机制），能同步的则同步***

不过有些场景实在没办法避免异步任务的出现，因此我们还是要对异步任务进行一定的**设计**或者**控制**。

我们罗列了一些异步任务的场景

# 2. 文档转化 

## 2.1 流程与代码

1. 用户上传了一批文档；
2. API保存文件后，发送消息到worker；
3. worker调用转换/抽取服务，并将文档状态回写到数据库；
4. 更新完文档状态后，会再检查任务状态，如果任务内的所有文件都处理完成则将Task置位完成；

伪代码如下:

```python
# api.py
def create_extract_tasks(task_name, files):
  file_models = save_file(files, status="PROCESS")  # class File(BaseModel):
  task_id = create_task(task_name)
  for f in file_models:
    extract.delay(f.id)
  commit()
```

```python
# task.py
@app.task()
def extract(file_id):
  file = get_file_entity(file_id)
  # 抽取并更新文件状态
  try:
	  send_request_to_third_for_extract(file.uniquename)
  except Exception as e:
    logger.exception(e)
    update_file(file.id, "FAIL")
  else:
    update_file(file.id, "SUCCESS")
  
  # 更新 task 状态，根据 task 里面所有的file状态来更新task
  update_task_status_based_on_files(file.task_id)

def update_task_status_based_on_files(task_id):
  files = get_file_by_task_id(task_id)
  # logic here
  status = get_status(files)
  # login end
  update_task(task_id, status=status)
```

你看出问题了吗？

## 2.2 问题与解决方法

### 2.2.0 尽早提交

第一个问题就是状态问题，在task中可能没有找到保存的`FileModel`

```python
# api.py
def create_extract_tasks(task_name, files):
  file_models = save_file(files, status="PROCESS")
  task_id = create_task(task_name)
  commit()
  for f in file_models:
    extract.delay(f.id)
```

第二个问题还是数据不一致的情况。

在task中，多事务同时去查询并更新，如果并发过高，可能会发生**[奇怪的问题]( ##6.1 数据库并发)**。

### 2.2.1 子任务

因此我们可以将**更新状态**放到所有任务的最后。

但是，`def extract(file_id)`这个方法是抽取每一篇文档，因此我们应该对其进行改造

```python
@app.task
def extract_files(file_ids):
  files = get_file_entity(file_ids)
  # 抽取并更新文件状态
  for file in files:
    try:
      send_request_to_third_for_extract(file.uniquename)
    except Exception as e:
      logger.exception(e)
      update_file(file.id, "FAIL")
    else:
      update_file(file.id, "SUCCESS")
  # 更新 task 状态，根据task里面所有的file状态来更新task
  update_task_status_based_on_files(file.task_id)
```

等等，好像有什么不对，虽然是异步了，不过在一个任务中去抽取好像直接拉低了系统的并发效率，没有运用起多worker的优势啊！

这时候，我们可以使用**子任务**，顾名思义，在任务里面再派发任务，等任务完成了，再进行下一波的操作。伪代码如下：

```python
@app.task
def extract_files(file_ids):
  files = get_file_entity(file_ids)
  tasks = list()
  # 抽取并更新文件状态
  for file in files:
    tasks.append(extract.delay(file.id))

 	# 确保任务已经都完成了
  for t in tasks:
    t.get()

  # 更新 task 状态，根据task里面所有的file状态来更新task
  update_task_status_based_on_files(file.task_id)

@app.task()
def extract(file_id):
    try:
      send_request_to_third_for_extract(file.uniquename)
    except Exception as e:
      logger.exception(e)
      update_file(file.id, "FAIL")
    else:
      update_file(file.id, "SUCCESS")
```

这种方法理论可行，不过Celery确不希望你这么做：

```bash
[2022-04-22 21:21:39,078: ERROR/ForkPoolWorker-8] Task task.a[4e85803e-1198-4b5c-8b6f-3d7c98efe6de] raised unexpected: RuntimeError('Never call result.get() within a task!\nSee http://docs.celeryq.org/en/latest/userguide/tasks.html#task-synchronous-subtasks\n')
Traceback (most recent call last):
  File "/Users/zinklu/.virtualenv/flask_template/lib/python3.8/site-packages/celery/app/trace.py", line 451, in trace_task
    R = retval = fun(*args, **kwargs)
  File "/Users/zinklu/.virtualenv/flask_template/lib/python3.8/site-packages/celery/app/trace.py", line 734, in __protected_call__
    return self.run(*args, **kwargs)
  File "/Users/zinklu/tmp/task.py", line 9, in a
    res.get()
  File "/Users/zinklu/.virtualenv/flask_template/lib/python3.8/site-packages/celery/result.py", line 210, in get
    assert_will_not_block()
  File "/Users/zinklu/.virtualenv/flask_template/lib/python3.8/site-packages/celery/result.py", line 38, in assert_will_not_block
    raise RuntimeError(E_WOULDBLOCK)
RuntimeError: Never call result.get() within a task!
See http://docs.celeryq.dev/en/latest/userguide/tasks.html#task-synchronous-subtasks
```

存在这种限制理由很简单，如果只有一个worker，在这个worker中去发送任务然后阻塞等待任务完成，那谁去完成这个被发送的任务。

不过如果你足够自信，worker够多，也可以尝试直接无视这个报错。

```python
  for t in tasks:
    t.get(disable_sync_subtasks=False)
```

### 2.2.2 数据库锁

还有一种比较合理的方式就是数据库的**排他(X)锁**。

> 使用共享(S)锁能解决这个问题吗？

这个问题存在的原因是由于我们**读取并保存了其他事务还没来得及更新的数据**。

如果我们让事务**顺序读取**，是不是就不会出问题了呢。

参考代码：

```python
# task.py
@app.task()
def extract(file_id):
    file = get_file_entity(file_id)
    # 抽取并更新文件状态
    try:
        send_request_to_third_for_extract(file.uniquename)
    except Exception as e:
        logger.exception(e)
        update_file(file.id, "FAIL")
    else:
        update_file(file.id, "SUCCESS")
  
    # 更新 task 状态，根据 task 里面所有的file状态来更新task
    update_task_status_based_on_files(file.task_id)

def update_task_status_based_on_files(task_id):
    task = get_task_for_update(task_id)  # 加上排他锁，准备更新task
    
    # 不使用快照读取，使用当前读 - 变相降低了隔离级别(应当在更新前再做一次提交的)
    files = get_file_by_task_id_lock_share_mode(task_id)  

    # logic here
    status = get_status(files)
    # login end
    update_task(task_id, status=status)
```

[数据库状态](##6.2 数据库并发(使用排他锁))

> 参考：
>
> ​	SQLALChemy中如何使用锁：[文档](https://docs.sqlalchemy.org/en/14/orm/query.html?highlight=sqlalchemy%20orm%20query%20with_for_update#sqlalchemy.orm.Query.with_for_update)

### 2.2.3 Group

使用数据库锁有的时候不是一个好选择，控制不好可能会变成死锁啊什么的。

似乎还是在文档转化后统一更新文档状态比较好，不过子任务又不合适。

于是就有了Celery的[工作流](https://docs.celeryq.dev/en/stable/getting-started/next-steps.html#canvas-designing-work-flows)。



我们可以使用Celery提供的[Group](https://docs.celeryq.dev/en/stable/userguide/canvas.html#groups)和[Chain](https://docs.celeryq.dev/en/stable/userguide/canvas.html#chains)等工具来解决当前场景面临的问题：

- Chian可以将任务串联起来执行

- Group可以将任务打包并分发
- Chord可以在所有任务完成后进行回调

给出一个可运行的代码示例：

```python
import time

from celery import Celery
from celery.canvas import chain, chord, group

app = Celery(
    "task",
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0', # 一定要设置
)

@app.task()
def workflow():
    task_id = 1 # 模拟task
    files = [1, 2, 3, 4] # 模拟files
    # 将所有文件的抽取任务打包成group,
    extract_groups = group([extract.si(i) for i in files]) 
    
    # chain 一下
    # .s 方法是创建一个签名对象，.si 方法则是忽略上一个消息的处理结果，否则上一个结果将作为第一个参数传入后续函数中
    c = extract_groups | update.si(task_id) # 同 chain(extract_groups, update.si(task_id))
    c.delay()

    print('workflow triiged!!')


@app.task()
def extract(file_id):
    print(f'extract file ... {file_id}')
    time.sleep(1)
    print(f"update file status .... and commit ")


@app.task()
def update(task_id):
    print(f'update task {task_id}')

workflow.delay()
```

```bash
# 启动服务
celery -A task.app worker -E --loglevel DEBUG
```

# 3. 数据导入/导出

## 3.1 流程与代码

1. 上传文件
2. 发送消息给worker
3. worker进行校验与导入

```python
# api.py
def import_file(file):
    file_entity = save_file(file) # commit
    validate_and_import(file_entity.id)
```

```python
# task.py
@app.task()
def validate_and_import(file_id):
    file = get_file(file_id)
    validate(file)
    imports(file)
```

## 3.2 问题与解决方法

代码没有任何问题，不过试想一下如果用户导入了一篇文档，后台处理之后杳无音讯，那会怎样？

> Unix哲学，“没有消息就是好消息”，在这里不适用。

应该引入**任务**的机制来告诉用户导入、导出的结果、进度、日志等。

```python
# api.py
def import_file(file):
  task_id = create_task() # 在api返回之前必须先创建任务让用户能够看到
  file_entity = save_file(file) # commit
  validate_and_import(task_id, file_entity.id)
```

```python
# task.py
@app.task()
def validate_and_import(task_id, file_id):
    task = get_task(task_id)
    file = get_file(file_id)
    validate_log = validate(file)
	write_logs_to_task(task_id, validate_log)
    import_log = imports(file)
    write_logs_to_task(task_id, import_log)
```

当然，上面的代码是彻头彻尾的伪代码，我们不应该在导入后再写入代码，而是应该一边导入，一边写入。或者按批次导入、写入。

# 4. 定时任务

## 4.1 流程与代码

Clery [beat](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html) 允许触发定时任务，定时任务没有特殊的流程，它定时触发，如下：

```python
# task.py
@app.task()
def beat_task():
    past = get_last_poll_time()
    now = datetime.datetime.now()
    to_be_created = poll_for_new_created(past, now)
    create_somthing(to_be_created)
    update_last_poll_time(now)
```

## 4.2 问题与解决方法

在一般情况下，我们不希望在上一个定时任务没有处理完成时去触发下一个定时任务，因此我们应该引入其他机制来跳过或者延迟这个任务（除非你明确有这种场景）

1. 跳过任务

   跳过任务比较简单，我们只需要使用**锁**就可以完成，由于涉及到多进程，因此应该使用Redis或者其他手段来支持；给出一个简单的实例，请酌情修改：

   ```python
   redis_cli = redis() # init a redis client
   
   @app.task()
   def beat_task():
     key = f"TASK_FLAG_beat_task"
     if not redis_cli.set(key, "1", ex=600, nx=True):
       logger.info(f"同样的任务正在执行，等待下一次触发: {key}")
       return
     try:
       past = get_last_poll_time()
       now = datetime.datetime.now()
       to_be_created = poll_for_new_created(past, now)
       create_somthing(to_be_created)
       update_last_poll_time(now)
     except BaseException as e:
       raise e
     finally:
       redis_cli.delete(key)
   ```

2. 延迟任务

   其实这个场景更加的复杂，你可以再获取锁结束之后再重新发送一个延迟消息。

   ```python
   if not redis_cli.set(key, "1", ex=600, nx=True):
     logger.info(f"同样的任务正在执行，等待下一次触发: {key}")
     beat_task.apply_async(countdown=60 * 30) # 延迟多少时间你自己定
     return
   ```

   不过这种方式总感觉挺怪的，我感觉比较好的做法是专门设置一个队列，专门有一个worker去监听这个队列，实现顺序执行。

   ```python
   @app.task(queue="beat_task")
   def beat_task():
   	...
   ```

   ```bash
   # 启动命令
   celery -A task.app worker -E --loglevel DEBUG -Q beat_task  # 指定监听 Q 队列
   
   # 如果你不使用 -Q 直接使用Celery启动，请确保将beat_task队列排除监听
   celery -A task.app worker -E --loglevel DEBUG -X beat_task  # 去除对 Q 队列的监听
   ```

# 5. 总结

总之，还是那句话，可以不异步就不异步，异步只会增加系统的复杂度，不过如果确实要用异步，请一定要思考并发可能出现的技术问题和一些易用性的问题。

其他场景欢迎补充，本文档持续更新。

# 6. 附录

## 6.1 数据库并发

线程中的并发情形

| 线程1                                                     | 线程2                                                     | 备注                           |
| --------------------------------------------------------- | --------------------------------------------------------- | ------------------------------ |
| begin;                                                    | begin;                                                    |                                |
| update_file_status<br />1, done, <br />2, processing      | update_file_status<br />1, processing, <br />2, done      | 不触发锁，因为更新的是不同文件 |
| get_file_by_task_id<br />1, done,<br />2, processing      | get_file_by_task_id<br />1, processing, <br />2, done     | 不触发锁，快照读               |
| UPDATE task SET status = "processing" WHERE task_id = xxx |                                                           | 触发数据库锁                   |
| commit;                                                   | UPDATE task SET status = "processing" WHERE task_id = xxx |                                |
|                                                           | commit;                                                   |                                |

## 6.2 数据库并发(使用排他锁)

修改后的并发情形

| 线程1                                                     | 线程2                                                     | 备注                           |
| --------------------------------------------------------- | --------------------------------------------------------- | ------------------------------ |
| begin;                                                    | begin;                                                    |                                |
| update_file_status<br />1, done, <br />2, processing      | update_file_status<br />1, processing, <br />2, done      | 不触发锁，因为更新的是不同文件 |
| commit      | commit      | 不触发锁，因为更新的是不同文件 |
| select_task_for_update                                    |                                                           | 触发排他锁                     |
| get_file_by_task_id_lock_share_mode<br />1, done,<br />2, processing | | |
| UPDATE task SET status = "processing" WHERE task_id = xxx | | |
| commit;                                                   | | |
|                                     |             select_task_for_update                             | 触发排他锁                     |
| | get_file_by_task_id_lock_share_mode<br />1, done, <br />2, done | 不触发锁，快照读               |
| |                                                          | 触发数据库锁                   |
| | UPDATE task SET status = "processing" WHERE task_id = xxx |                                  |
| | commit;                                                   |                                |

> 这种情况是指望不上数据库的隔离级别去发挥作用的
> 拓展阅读：
> 	[Innodb中的事务隔离级别和锁的关系](https://tech.meituan.com/2014/08/20/innodb-lock.html)
> 	[你应该了解的MySQL锁分类](https://segmentfault.com/a/1190000023869573)
> 	[Innodb的多版本并发控制(MVCC)](https://segmentfault.com/a/1190000037557620)	
> 	[【原创】惊！史上最全的select加锁分析(Mysql)](https://www.cnblogs.com/rjzheng/p/9950951.html)

## 6.3 Celery 服务的部署

详见 [Flask文档](http://flask-docs.dics.datagrand.cn/docs/%E5%BC%82%E6%AD%A5%E4%BB%BB%E5%8A%A1/%E5%90%AF%E5%8A%A8%E6%96%B9%E5%BC%8F.html)

