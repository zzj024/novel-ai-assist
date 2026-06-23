def test_init_default_config_creates_file(tmp_config_path):
    """config.json不存在时，init_default_config()应创建它并写入默认值"""
    # tmp_config_path 指向一个不存在的路径
    assert not tmp_config_path.exists()

    # 调用初始化方法（还没写，但是先定义它的行为）
    from config import init_default_config
    result = init_default_config(tmp_config_path)

    # 验证文件被创建
    assert tmp_config_path.exists()
    # 验证内容是Deepseek默认配置
    assert result.ai_provider == "deepseek"
    assert result.api_base == "https://api.deepseek.com/v1"
    assert result.auto_scan_interval == 3600

def test_load_config_reads_existing_file(tmp_config_path,sample_config_data):
    """load_config 应正确读取已存在的配置文件"""
    # 先手动写入一个配置道临时路径
    tmp_config_path.parent.mkdir(parents=True)
    tmp_config_path.write_text(
        __import__("json").dumps(sample_config_data, ensure_ascii=False),
          encoding="utf-8",
    )
    # 调用load_config读取
    from config import load_config
    result = load_config(tmp_config_path)
    
    # 验证返回的 Settings 对象字段与原数据一致
    assert result.novel_dir == sample_config_data["novel_dir"]
    assert result.ai_provider == sample_config_data["ai_provider"]
    assert result.api_key == sample_config_data["api_key"]
    assert result.model == sample_config_data["model"]
    assert result.auto_scan_interval == sample_config_data["auto_scan_interval"]

def test_load_config_fills_missing_fields(tmp_config_path):
    """配置文件中缺失字段应自动用默认值填充"""
    # 只写一个字段，模拟部分配置
    tmp_config_path.parent.mkdir(parents=True)
    tmp_config_path.write_text(
        '{"ai_provider": "ollama"}',
        encoding="utf-8",
    )
    from config import load_config
    result = load_config(tmp_config_path)

    # 写入的字段保留
    assert result.ai_provider == "ollama"
    # 缺失的字段用默认值
    assert result.api_base == "https://api.deepseek.com/v1"
    assert result.auto_scan_interval == 3600
    assert result.novel_dir == "."
    assert result.language == "zh"

def test_save_config_writes_to_disk(tmp_config_path, sample_config_data):
    """save_config 应将修改后的配置持久化到文件"""
    # 先写入一份完整配置
    tmp_config_path.parent.mkdir(parents=True)
    tmp_config_path.write_text(
        __import__("json").dumps(sample_config_data, ensure_ascii=False),
        encoding="utf-8",
    )
    # 读取 → 修改 model → 保存
    from config import load_config, save_config
    settings = load_config(tmp_config_path)
    settings.model = "deepseek-reasoner"
    save_config(settings, tmp_config_path)

    # 重新读取，验证 model 已更新，其他字段不变
    reloaded = load_config(tmp_config_path)
    assert reloaded.model == "deepseek-reasoner"
    assert reloaded.ai_provider == "deepseek"
    assert reloaded.api_base == "https://api.deepseek.com/v1"

def test_api_key_masking(tmp_config_path, sample_config_data):
    """masked_api_key 应脱敏显示，保留前6后2"""
    # 准备一个示例key
    data = {**sample_config_data, "api_key": "sk-abcdefghijklmnop"}
    tmp_config_path.parent.mkdir(parents=True)
    tmp_config_path.write_text(
        __import__("json").dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )
    from config import load_config
    settings = load_config(tmp_config_path)
    masked = settings.masked_api_key
    assert masked == "sk-abc****op"
    assert len(masked) == 12  

def test_load_config_handles_corrupted_file(tmp_config_path):
    """配置文件损坏时应抛出 ConfigError"""
    tmp_config_path.parent.mkdir(parents=True)
    tmp_config_path.write_text("不是 JSON 数据", encoding="utf-8")

    from config import load_config, ConfigError
    import pytest

    with pytest.raises(ConfigError):
        load_config(tmp_config_path)


#
















