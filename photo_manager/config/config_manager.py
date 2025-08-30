"""
Configuration manager for the photo manager application.
Handles loading, saving, and managing configuration files.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from .default_config import DEFAULT_CONFIG


class ConfigManager:
    """Manages configuration loading and saving."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to configuration file. If None, uses default locations.
        """
        self.config_path = config_path
        self.config = {}
        
    def load_config(self, directory_path: str) -> Dict[str, Any]:
        """
        Load configuration with hierarchical precedence:
        1. Directory-specific config file
        2. User-specified config file
        3. Default configuration
        
        Args:
            directory_path: Path to directory being managed
            
        Returns:
            Merged configuration dictionary
        """
        # Start with default config
        config = DEFAULT_CONFIG.copy()
        
        # Try to load user-specified config
        if self.config_path and os.path.exists(self.config_path):
            user_config = self._load_yaml(self.config_path)
            if user_config:
                config = self._merge_configs(config, user_config)
        
        # Try to load directory-specific config
        dir_config_path = os.path.join(directory_path, 'config.yaml')
        if os.path.exists(dir_config_path):
            dir_config = self._load_yaml(dir_config_path)
            if dir_config:
                config = self._merge_configs(config, dir_config)
        
        self.config = config
        return config
    
    def load_auto_tag_template(self, template_path: Optional[str] = None, 
                              directory_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Load auto-tagging template.
        
        Args:
            template_path: Explicit template path
            directory_path: Directory to check for auto_tag_template.yaml
            
        Returns:
            Template dictionary or None if no template
        """
        template_file = None
        
        # Check explicit template path first
        if template_path and os.path.exists(template_path):
            template_file = template_path
        # Check directory for template
        elif directory_path:
            dir_template = os.path.join(directory_path, 'auto_tag_template.yaml')
            if os.path.exists(dir_template):
                template_file = dir_template
        
        if template_file:
            return self._load_yaml(template_file)
        return None
    
    def save_config(self, directory_path: str, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Save current configuration to directory.
        
        Args:
            directory_path: Directory to save config in
            config: Optional config dict, uses self.config if None
            
        Returns:
            True if successful
        """
        try:
            if config is None:
                config = self.config
                
            config_path = os.path.join(directory_path, 'config.yaml')
            with open(config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, indent=2)
            
            return True
            
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def add_hotkey(self, key_combination: str, tag_category: str, tag_name: str) -> bool:
        """
        Add a new hotkey to the configuration.
        
        Args:
            key_combination: Key combination (e.g., 'b', 'shift_g', 'ctrl_t')
            tag_category: Category for the tag
            tag_name: Name of the tag
            
        Returns:
            True if successful
        """
        try:
            if 'hotkeys' not in self.config:
                self.config['hotkeys'] = {'custom': {}}
            elif 'custom' not in self.config['hotkeys']:
                self.config['hotkeys']['custom'] = {}
                
            self.config['hotkeys']['custom'][key_combination] = f"{tag_category}/{tag_name}"
            return True
            
        except Exception as e:
            print(f"Error adding hotkey: {e}")
            return False
    
    def get_hotkeys(self) -> Dict[str, str]:
        """Get custom hotkey mappings."""
        return self.config.get('hotkeys', {}).get('custom', {})
    
    def get_slideshow_config(self) -> Dict[str, Any]:
        """Get slideshow-specific configuration."""
        return self.config.get('slideshow', {})
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration."""
        return self.config.get('database', {})
    
    def get_ui_config(self) -> Dict[str, Any]:
        """Get UI configuration."""
        return self.config.get('ui', {})
    
    def _load_yaml(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Load YAML file safely."""
        try:
            with open(file_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading YAML file {file_path}: {e}")
            return None
    
    def _merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively merge configuration dictionaries.
        
        Args:
            base: Base configuration
            override: Configuration to merge in (takes precedence)
            
        Returns:
            Merged configuration
        """
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
                
        return result


class AutoTagTemplate:
    """Handles auto-tagging template parsing and application."""
    
    def __init__(self, template_dict: Dict[str, Any]):
        """Initialize with template dictionary from YAML."""
        self.fixed_tags = template_dict.get('fixed_tags', {})
        self.patterns = template_dict.get('auto_tag_templates', [])
        
    def has_fixed_tags(self) -> bool:
        """Check if template has fixed tags."""
        return bool(self.fixed_tags)
    
    def has_pattern_matching(self) -> bool:
        """Check if template has pattern matching enabled."""
        if not self.patterns:
            return False
        # Check for explicit "none" pattern
        for pattern_config in self.patterns:
            if pattern_config.get('pattern') == 'none':
                return False
        return True
    
    def get_fixed_tags(self) -> Dict[str, List[str]]:
        """
        Get fixed tags formatted for application.
        
        Returns:
            Dictionary with tag category as key and list of tag names as value
        """
        formatted_tags = {}
        
        for category, tags in self.fixed_tags.items():
            if isinstance(tags, str):
                # Single tag as string
                formatted_tags[category] = [tags]
            elif isinstance(tags, list):
                # Multiple tags as list
                formatted_tags[category] = tags
            
        return formatted_tags
    
    def extract_pattern_tags(self, file_path: str, base_directory: str) -> Dict[str, List[str]]:
        """
        Extract tags from file path using template patterns.
        
        Args:
            file_path: Full path to image file
            base_directory: Base directory being scanned
            
        Returns:
            Dictionary with extracted tags by category
        """
        # TODO: Implement pattern matching logic
        # This will parse the file path against template patterns
        # and extract tags based on the mapping configuration
        return {}


def create_default_config(directory_path: str) -> bool:
    """Create a default configuration file in the specified directory."""
    try:
        config_path = os.path.join(directory_path, 'config.yaml')
        
        with open(config_path, 'w') as f:
            yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, indent=2)
            
        print(f"Default configuration created: {config_path}")
        return True
        
    except Exception as e:
        print(f"Error creating default config: {e}")
        return False


def create_example_auto_tag_template(directory_path: str) -> bool:
    """Create an example auto-tag template in the specified directory."""
    try:
        template_path = os.path.join(directory_path, 'auto_tag_template.yaml')
        
        example_template = {
            'fixed_tags': {
                'event_tags': ['vacation', 'beach'],
                'people_tags': ['family'],
                'photographer': 'Dad'
            },
            'auto_tag_templates': [
                {
                    'pattern': '/{year}/{photographer}/{people}-{scene}*.{ext}',
                    'mapping': {
                        'photographer': 'photographer',
                        'people': 'people_tags', 
                        'scene': 'scene_tags'
                    }
                }
            ]
        }
        
        with open(template_path, 'w') as f:
            yaml.dump(example_template, f, default_flow_style=False, indent=2)
            
        print(f"Example auto-tag template created: {template_path}")
        return True
        
    except Exception as e:
        print(f"Error creating auto-tag template: {e}")
        return False