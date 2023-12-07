---
title: "在数据库中处理树形数据结构"
date: "2023-12-05T20:57:51+08:00"
draft: false
description: 
summary: 理解 Nested Set Model(嵌套集合模型) 和 modified preorder tree traversal algorithm(MPTT-预排序遍历树算法)
isMath: false
---

# 前言

自关联表，通常都有一个 `parent_id` 字段，来形成层级结构，这里的层级结构我们先认为只能有**零个或一个父节点**，且**无闭环**。

有时业务上需要知道某一个节点的所有节点，对于 PG 来说，它很早就支持了`with recursive` 的查询语句。而对于 mysql 而言，在 mysql8 之前，没有办法使用 `with recursive` 进行查询，如果要使用存储过程来处理的话，他看起来可能是[这样](https://stackoverflow.com/questions/20215744/how-to-create-a-mysql-hierarchical-recursive-query):

```sql
select  id,
        name,
        parent_id 
from    (select * from products
         order by parent_id, id) products_sorted,
        (select @pv := '19') initialisation
where   find_in_set(parent_id, @pv)
and     length(@pv := concat(@pv, ',', id))
```

不考虑性能问题，这个语句特异性太强，可能无法在其他数据库直接运行，比如国产数据库可能就无法支持 `find_in_set` 方法。

对于TOB软件来说，为了适配多种数据库，必须要降低SQL语句的特异性。一个通用的做法是在编程语言中来保存变量、递归查询所有组：

```python
def find_all_children(target_id) -> List[int]:
    result = []
    children_ids = (target_id,)

    while children_ids:
        cr.execute(
            "SELECT id, parent_id FROM products WHERE parent_id IN %s;",
            children_ids,
        )
        children_ids = (r[0] for r in cr.fetchall())
        result.extend(children_ids)

    return result
```

众所周知，在循环里面去多次查询数据库是一个费时费力的操作。

本文介绍了一种叫做**嵌套集合模型**的高级数据结构，通过在树形结构上增加额外两个字段来记录信息，并通过新的 JOIN 语句来进行快速查询。

# 嵌套集合模型（**Nested Set Model**）

嵌套集合模型将树形结构上的节点看做**集合**，它们的继承关系看做为集合之间的**嵌套**，如下图：

![Untitled](Untitled.png)

通过嵌套关系，我们很容易看出一个节点拥有多少递归的子节点。同时，通过给通过给某一个集合的 **左** 和 **右** 来进行编码，来确定集合的范围，这样便能够一口气筛选出它的所有子集合。

编码规则如下，每一个集合的 **左** 和 **右** 的区间永远包含其所有子类的区间：

![Untitled](Untitled%201.png)

同时，集合并不破坏原来树形结构：

![Untitled](Untitled%202.png)

通过这种编码，我们可以通过一个简单的 SQL 语句来查询出某个节点的所有子节点。这种使用边界直觉框选子节点的算法被被称为**预排序遍历树算法（modified preorder tree traversal algorithm）**。

接下来就一起来看下具体如何使用嵌套集合模型来对树进行操作。

# 数据准备

```sql
CREATE TABLE t_group (
    id INT NOT NULL,
    name VARCHAR(64) NOT NULL COMMENT '组织名称',
    parent_id INT NOT NULL COMMENT '上级组，为 0 时认为是顶级组',
    lft INT NOT NULL,
    rgt INT NOT NULL,
    PRIMARY KEY (id)
);
```

```sql
INSERT INTO t_group
  	(id, name, parent_id, lft, rgt)
VALUES
    (1, '总公司', 0, 1, 22),
    (2, '财务部', 1, 2, 3),
    (3, '技术部', 1, 4, 9),
    (4, '运维部', 3, 5, 6),
    (5, '产品技术部', 3, 7, 8),
    (6, '市场部', 1, 10, 21),
    (7, '华东市场部', 6, 11, 14),
    (8, '华北市场部', 6, 15, 20),
    (9, '华北市场一部', 8, 16, 17),
    (10, '华北市场二部', 8, 18, 19),
    (11, '华东市场一部', 7, 12, 13);
```

# 获取整棵树

为了获取整棵树，我们不再使用 parent_id 进行 JOIN（这只能获取到一层子节点），而是直接使用 lft 和 rgt 框定返回，查询所有子节点。

最后，使用 lft 进行排序，能够获取排序好的树:

```sql
SELECT 
	node.name   AS node_name,
	parent.name AS parent_name
FROM 
	t_group parent
JOIN
	t_group node ON node.lft BETWEEN parent.lft AND parent.rgt
WHERE
	parent.name = '市场部'
ORDER BY node.lft;
```

| node_name | parent_name |
| --- | --- |
| 市场部 | 市场部 |
| 华东市场部 | 市场部 |
| 华东市场一部 | 市场部 |
| 华北市场部 | 市场部 |
| 华北市场一部 | 市场部 |
| 华北市场二部 | 市场部 |

# 获取所有叶子节点（无子节点的节点）

叶子节点最重要的特征就是它的 rgt 和 lft 只差 1

```sql
SELECT 
	node.name AS node_names
FROM 
	t_group node
WHERE 
	node.rgt = node.lft + 1;
```

| node_name |
| --- |
| 财务部 |
| 运维部 |
| 产品技术部 |
| 华北市场一部 |
| 华北市场二部 |
| 华东市场一部 |

# 获取一整条完整路径

和获取完整树一样，获取一条路径（通过node找顶层parent）步骤也是一样的，JOIN 的条件不变。

过滤条件加在 node 上即可。

```sql
SELECT 
	parent.name AS parent_name,
	node.name   AS node_name
FROM 
	t_group parent
JOIN
	t_group node ON node.lft BETWEEN parent.lft AND parent.rgt
WHERE
	node.name = '产品技术部'
ORDER BY parent.lft;
```

| node_name | parent_name |
| --- | --- |
| 总公司 | 产品技术部 |
| 技术部 | 产品技术部 |
| 产品技术部 | 产品技术部 |

# 获取节点深度

当我们使用这种自关联查询时，每一个节点的所有子节点都会被查询一次，因此对于一个节点来说，它出现的次数就等于它的深度。

```sql
SELECT
	node.name     AS node_name,
	COUNT(*) - 1  AS depth
FROM 
	t_group parent
JOIN
	t_group node ON node.lft BETWEEN parent.lft AND parent.rgt
GROUP BY node.name, node.lft
ORDER BY node.lft;
```

| name | depth |
| --- | --- |
| 总公司 | 0 |
| 财务部 | 1 |
| 技术部 | 1 |
| 运维部 | 2 |
| 产品技术部 | 2 |
| 市场部 | 1 |
| 华东市场部 | 2 |
| 华东市场一部 | 3 |
| 华北市场部 | 2 |
| 华北市场一部 | 3 |
| 华北市场二部 | 3 |

# 获取子树的深度

想要知道深度，必须进行全量的 JOIN 查询，任何的查询条件都会破坏某节点的出现次数。为了能够查询子树的深度，我们需要单独查询某个节点的深度

```sql
-- 下面的SQL可以查询某子节点的深度
SELECT
	node.name AS node_name
	,COUNT(*) - 1 AS depth
FROM 
	t_group parent
JOIN
	t_group node ON
	node.lft BETWEEN parent.lft AND parent.rgt
WHERE 
	node.name = '市场部'
GROUP BY
	node.name,
	node.lft
ORDER BY
	node.lft;
```

随后再用这个查询作为子句进行查询，得出该节点的其他子节点的层级，例如

```sql
SELECT 
	node.name,
	(COUNT(*) - sub_tree.depth - 1) AS depth
FROM 
	t_group parent
INNER JOIN
	t_group node ON
	node.lft BETWEEN parent.lft AND parent.rgt
INNER JOIN 
	(
	SELECT
		node.name AS node_name,
		COUNT(*) - 1 AS depth,
		node.lft AS lft,
		node.rgt AS rgt
	FROM
		t_group parent
	JOIN
	t_group node ON
		node.lft BETWEEN parent.lft AND parent.rgt
	WHERE
		node.name = '市场部'
	GROUP BY
		node.name,
		node.lft,
		node.rgt
	ORDER BY
		node.lft
) sub_tree ON
	node.lft BETWEEN sub_tree.lft AND sub_tree.rgt
GROUP BY
	node.name,
	node.lft,
	sub_tree.depth
ORDER BY
	node.lft;
```

| name | depth |
| --- | --- |
| 市场部 | 0 |
| 华东市场部 | 1 |
| 华东市场一部 | 2 |
| 华北市场部 | 1 |
| 华北市场一部 | 2 |
| 华北市场二部 | 2 |

# 获取某个节点的直接子节点

当我们拿到子树的节点和深度后，该节点的直接子节点就是深度等于 1 的所有节点，因此可以使用 HAVING 作为条件进行过滤

```sql
SELECT 
	node.name,
	(COUNT(*) - sub_tree.depth - 1) AS depth
FROM 
	t_group parent
INNER JOIN
	t_group node ON
	node.lft BETWEEN parent.lft AND parent.rgt
INNER JOIN 
	(
	SELECT
		node.name AS node_name,
		COUNT(*) - 1 AS depth,
		node.lft AS lft,
		node.rgt AS rgt
	FROM
		t_group parent
	JOIN
	t_group node ON
		node.lft BETWEEN parent.lft AND parent.rgt
	WHERE
		node.name = '市场部'
	GROUP BY
		node.name,
		node.lft,
		node.rgt
	ORDER BY
		node.lft
) sub_tree ON
	node.lft BETWEEN sub_tree.lft AND sub_tree.rgt
GROUP BY
	node.name,
	node.lft,
	sub_tree.DEPTH
HAVING (COUNT(*) - sub_tree.depth - 1) = 1
ORDER BY
	node.lft;
```

| name | depth |
| --- | --- |
| 华东市场部 | 1 |
| 华北市场部 | 1 |

# 添加兄弟节点

加入希望添加一个新的节点，比如在技术部这一层增加一个人事部

![Untitled](Untitled%203.png)

那么我们可以这么写:

```sql
-- 添加人事部
LOCK TABLE t_group WRITE;

BEGIN;

SELECT
	@myRight := rgt,
	@parentId := parent_id
FROM
	t_group
WHERE
	name = '技术部';

UPDATE t_group SET rgt = rgt + 2 WHERE rgt > @myRight;
UPDATE t_group SET lft = lft + 2 WHERE lft > @myRight;

INSERT INTO t_group(name, parent_id, lft, rgt) VALUES('人事部', @parentId, @myRight + 1, @myRight + 2);

COMMIT;

UNLOCK TABLES;
```

对于新增加的人事部来说，由于它是一个新增的节点，而且它被安排在技术部的右边，因此原本技术部右边的所有节点统一往右边挪2位（左右节点都 +2），然后在安排人事部使用 `10,11` 作为其左右值。

为了降低数据库特异性，我们需要使用编程语言和SQL相结合，且需要 ORM 框架的协助。对于 Python 来说 SQLAlchemy 是不二之选。

我们先定义 SQLAlchemy 的对象

```python
import sqlalchemy as sa

engine = sa.create_engine("mysql+pymysql://USER:PWD@HOST:PORT/DB") # 变成你自己的链接

metadata = sa.MetaData(engine)

group = sa.Table(
    "t_group",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("name", sa.VARCHAR(64), nullable=False, comment="组织名称"),
    sa.Column(
        "parent_id",
        sa.Integer,
        nullable=False,
        comment="上级组，为 0 时认为是顶级组",
        default=0,
    ),
    sa.Column("lft", sa.Integer, nullable=False),
    sa.Column("rgt", sa.Integer, nullable=False),
)
```

然后参考以下代码来进行插入组（后面将仅用 Python 代码作为示例）

```python
distribute_lock.lock() # 为了防止客户环境没有 LOCK TABLE 的权限，假设我们使用 redis 或者 zk 实现了一个分布式锁

with engine.begin() as conn:
    conn: sa.engine.Connection

    res = conn.execute(group.select(group.c.name == "人事部"))
    hr = res.first()

    hr_lft, hr_id = hr.lft, hr.id

    conn.execute(
        group.update().where(group.c.rgt > hr_lft).values(rgt=group.c.rgt + 2)
    )
    conn.execute(
        group.update().where(group.c.lft > hr_lft).values(lft=group.c.lft + 2)
    )

    conn.execute(
        group.insert(),
        name="HRPB",
        parent_id=hr_id,
        lft=hr_lft + 1,
        rgt=hr_lft + 2,
    )

distribute_lock.unlock()
```

# 添加子节点

假如此时我们希望在人事部下面再添加新的节点，比如我们希望再添加一个 HRBP 的部门：

![Untitled](Untitled%204.png)

稍微修改一下代码即可

```python
distribute_lock.lock()

with engine.begin() as conn:
    conn: sa.engine.Connection

    res = conn.execute(group.select(group.c.name == "人事部"))
    hr = res.first()

    hr_lft, hr_id = hr.lft, hr.id

    conn.execute(
        group.update().where(group.c.rgt > hr_lft).values(rgt=group.c.rgt + 2)
    )
    conn.execute(
        group.update().where(group.c.lft > hr_lft).values(lft=group.c.lft + 2)
    )

    conn.execute(
        group.insert(),
        name="HRPB",
        parent_id=hr_id,
        lft=hr_lft + 1,
        rgt=hr_lft + 2,
    )

distribute_lock.unlock()
```

如果该节点已经有了其他子节点，那么这个方法也可以在其他已有的子节点前新增一个子节点。

# 清空子节点

清空节点正好和添加节点相反，如果要清空一个节点的子节点，首先需要删除他 lft 和 rgt 内的所有子节点，再将右边的所有节点都减去原来子节点的宽度：

```python
distribute_lock.lock()

with engine.begin() as conn:
    conn: sa.engine.Connection

    res = conn.execute(group.select(group.c.name == "人事部"))
    market = res.first()

    mk_lft, mk_rgt, width = market.lft, market.rgt, market.rgt - market.lft - 1

    conn.execute(
        group.delete().where(group.c.lft > mk_lft).where(group.c.rgt < mk_rgt)
    )

    conn.execute(
        group.update().where(group.c.rgt > mk_lft).values(rgt=group.c.rgt - width)
    )

    conn.execute(
        group.update().where(group.c.lft > mk_lft).values(lft=group.c.lft - width)
    )

distribute_lock.unlock()
```

# 删除节点

删除子节点和情况节点一样，只不过我们需要额外删除当前节点（使用Between），然后宽度发生变化，代码如下

```python
distribute_lock.lock()

with engine.begin() as conn:
    conn: sa.engine.Connection

    res = conn.execute(group.select(group.c.name == "人事部"))
    hr = res.first()

    hr_lft, hr_rgt, width = hr.lft, hr.rgt, hr.rgt - hr.lft + 1

    conn.execute(group.delete().where(group.c.lft.between(hr_lft, hr_rgt)))

    conn.execute(
        group.update()
        .where(group.c.rgt > hr_rgt)
        .values(rgt=group.c.rgt - width)
    )
    conn.execute(
        group.update()
        .where(group.c.lft > hr_rgt)
        .values(lft=group.c.lft - width)
    )

distribute_lock.unlock()
```

# 移动节点

有时我们希望将一个节点移动到另一个节点下，这种操作会比较复杂一些。我们需要进行如下几个步骤：

1. 该节点的右侧的节点需要减去该节点的宽度（和删除该节点时的操作一样）
2. 在目标节点下添加这个节点，同时移动目标节点右侧节点的值（和新建节点时的操作一样，只不过宽度可能不为 2 ）
3. 计算这个节点移动的距离，纠正该节点下所有子节点的左右值

当然还有一些细节，请看代码

```python
def move_node(node_name, target_node_name):
    distribute_lock.lock()

    with engine.begin() as conn:
        conn: sa.engine.Connection

        # 查询需要修改的节点，目标节点
        res = conn.execute(group.select(group.c.name == node_name))
        node = res.first()

        res = conn.execute(group.select(group.c.name == target_node_name))
        target = res.first()

        # 检查，如果目标节点是 node 的子节点（包含自身）则不允许这么设置（等于有了循环嵌套）
        if target.lft >= node.lft and target.rgt <= node.rgt:
            raise RuntimeError("目标节点不允许是该节点本身或该节点的子节点")

        node_lft, node_rgt, node_width = node.lft, node.rgt, node.rgt - node.lft + 1

        # 将所有的子节点（包含自身）更新为负数（暂时离开树，否则会被误修改）
        conn.execute(
            group.update()
            .where(group.c.lft.between(node_lft, node_rgt))
            .values(lft=-group.c.lft, rgt=-group.c.rgt)
        )

        # 首先先缩减修改节点右侧的所有节点的左右值（就当是删除了节点）
        conn.execute(
            group.update()
            .where(group.c.rgt > node_rgt)
            .values(rgt=group.c.rgt - node_width)
        )
        conn.execute(
            group.update()
            .where(group.c.lft > node_rgt)
            .values(lft=group.c.lft - node_width)
        )

        # 添加子节点，需要新增目标节点的右侧所有节点的左右值（相当于增加了宽度不为 2 的节点）
        res = conn.execute(group.select(group.c.name == target_node_name))
        target = res.first()

        target_lft, target_id = target.lft, target.id

        conn.execute(
            group.update()
            .where(group.c.rgt > target_lft)
            .values(rgt=group.c.rgt + node_width)
        )
        conn.execute(
            group.update()
            .where(group.c.lft > target_lft)
            .values(lft=group.c.lft + node_width)
        )

        # 计算需要修改的节点到目标节点的 offset，将移动节点下的所有子节点(包括自身)翻转为正数后再增加对应的偏移量
        offset = target_lft - node_lft + 1
        conn.execute(
            group.update()
            .where(group.c.lft < 0)
            .values(lft=-group.c.lft + offset, rgt=-group.c.rgt + offset)
        )
        # 最后更新更新节点的 parent_id
        conn.execute(
            group.update().where(group.c.id == node.id).values(parent_id=target_id)
        )

    distribute_lock.unlock()
```

参考:

[https://stackoverflow.com/questions/20215744/how-to-create-a-mysql-hierarchical-recursive-query](https://stackoverflow.com/questions/20215744/how-to-create-a-mysql-hierarchical-recursive-query)

[https://mikehillyer.com/articles/managing-hierarchical-data-in-mysql/](https://mikehillyer.com/articles/managing-hierarchical-data-in-mysql/)

[https://books.google.com/books?id=uw2lq2o4VbUC](https://books.google.com/books?id=uw2lq2o4VbUC)