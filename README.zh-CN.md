# cf-time-seams 中文说明

合并 NetCDF 文件前，检查真实时间坐标中的重复点、文件范围重叠、采样间隔和时间边界接缝。
支持 standard、proleptic_gregorian、julian、noleap、all_leap、360_day 日历及对应别名。
不同单位和起点可比较；不同日历会报错，不做隐式转换。

Python 3.11+。克隆后运行 `python -m pip install .`，再运行：

```sh
python examples/make_demo.py .demo
cf-time-seams ".demo/clean/*.nc" --step-seconds 86400 --json
cf-time-seams ".demo/gap/*.nc" --step-seconds 86400 --json
```

示例为人工构造的测试数据。第一条检查退出 0；第二条退出 1，指出缺失的一天。
`--monthly` 表示连续月份的相同日期和时刻，不自动处理月末日期；
`--check-bounds` 显式要求并检查每个文件的 time.bounds。
退出码 0=完整检查通过，1=发现问题，2=输入无效或检查未完成。

文件应属于同一条时间序列，不能把不同变量、空间分块或集合成员混在一起。
结果包含文件路径和从 0 开始的索引，分享报告前请检查路径是否敏感。
默认最多读取一百万个时间点并保存在内存中，不读取数据变量，不修改输入。
仅支持根变量和微秒精度，不支持闰秒日历、自定义日历、气候态或远程数据。
不验证物理量、空间网格、期望起止时间或科学结论。

运行测试：`python -m unittest discover -s tests -v`。
卸载：`python -m pip uninstall cf-time-seams`；示例目录和虚拟环境可自行删除。
完整参数、边界和替代工具见 [英文说明](README.md)。
