#!/usr/bin/env python3
"""
测试 Skill 版本与官方文档合规性
Test Skill version compliance with official documentation
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))


class TestSkillVersionCompliance(unittest.TestCase):
    """验证 Skill 版本符合官方要求"""
    
    def test_skill_version_format(self):
        """版本号格式应为语义化版本"""
        from weread_api import SKILL_VERSION
        
        # 应该是 x.y.z 格式
        parts = SKILL_VERSION.split('.')
        self.assertEqual(len(parts), 3, f"版本号应为 x.y.z 格式: {SKILL_VERSION}")
        
        for part in parts:
            self.assertTrue(part.isdigit(), f"版本号每部分应为数字: {SKILL_VERSION}")
    
    def test_skill_version_minimum(self):
        """版本号应 >= 1.0.6（官方最新版）"""
        from weread_api import SKILL_VERSION
        
        major, minor, patch = map(int, SKILL_VERSION.split('.'))
        
        # 官方 2026-11-17 发布 1.0.6
        self.assertGreaterEqual(major, 1, "主版本号应 >= 1")
        self.assertGreaterEqual(minor, 0, "次版本号应 >= 0")
        self.assertGreaterEqual(patch, 6, f"补丁版本应 >= 6（当前 {SKILL_VERSION}，官方 1.0.6）")
    
    def test_gateway_url_correct(self):
        """网关 URL 应为官方地址"""
        from weread_api import WEREAD_GATEWAY_URL
        
        expected = "https://i.weread.qq.com/api/agent/gateway"
        self.assertEqual(WEREAD_GATEWAY_URL, expected)
    
    def test_skill_version_sent_in_request(self):
        """请求应包含 skill_version 参数"""
        from unittest.mock import Mock, patch
        
        os.environ["WEREAD_API_KEY"] = "wrk-test-key"
        
        with patch('requests.Session.post') as mock_post:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.json.return_value = {"books": []}
            mock_post.return_value = mock_response
            
            from weread_api import WeReadApi, SKILL_VERSION
            api = WeReadApi()
            api._call("/test/api", param1="value1")
            
            # 验证请求包含正确参数
            call_args = mock_post.call_args
            request_body = call_args[1]["json"]
            
            self.assertIn("skill_version", request_body)
            self.assertEqual(request_body["skill_version"], SKILL_VERSION)
            self.assertEqual(request_body["api_name"], "/test/api")
            self.assertEqual(request_body["param1"], "value1")
        
        del os.environ["WEREAD_API_KEY"]
    
    def test_upgrade_info_handling_contract(self):
        """
        验证 upgrade_info 处理符合官方契约:
        - 不应抛出异常
        - 应返回有效业务数据
        - 应记录通知（可选验证）
        """
        from unittest.mock import Mock, patch
        
        os.environ["WEREAD_API_KEY"] = "wrk-test-key"
        
        response_with_upgrade = {
            "books": [{"bookId": "test123"}],
            "upgrade_info": {
                "message": "有新版本 1.0.7",
                "upgrade_url": "https://example.com/upgrade"
            }
        }
        
        with patch('requests.Session.post') as mock_post:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.json.return_value = response_with_upgrade
            mock_post.return_value = mock_response
            
            from weread_api import WeReadApi
            api = WeReadApi()
            
            # 应正常返回数据，不抛异常
            result = api._call("/shelf/sync")
            
            self.assertIn("books", result)
            self.assertEqual(result["books"][0]["bookId"], "test123")
            # upgrade_info 也在响应中（透传）
            self.assertIn("upgrade_info", result)
        
        del os.environ["WEREAD_API_KEY"]


if __name__ == '__main__':
    unittest.main(verbosity=2)
