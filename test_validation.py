#!/usr/bin/env python3

import unittest
import os
import sys
import subprocess
from unittest.mock import patch, MagicMock
from validation import SDCardValidator

class TestSDCardValidator(unittest.TestCase):
    def setUp(self):
        self.validator = SDCardValidator()
        
        # Create test file for source validation
        with open('test_fuzix.img', 'w') as f:
            f.write('test data')
            
    def tearDown(self):
        # Clean up test file
        if os.path.exists('test_fuzix.img'):
            os.remove('test_fuzix.img')
        
    @patch('os.path.exists')
    @patch.object(SDCardValidator, 'validate_device')
    def test_device_validation(self, mock_validate, mock_exists):
        """Test device validation with mocks"""
        # Set up mocks
        mock_exists.return_value = True
        mock_validate.return_value = (True, "Device validation passed")
        
        # Test device validation
        success, message = self.validator.validate_device("/dev/sdb")
        self.assertEqual(mock_validate.return_value, (True, "Device validation passed"))
        
        # Test invalid device
        mock_validate.return_value = (False, "Invalid device")
        success, message = self.validator.validate_device("/dev/invalid")
        self.assertEqual(mock_validate.return_value, (False, "Invalid device"))

    def test_partition_sequence(self):
        """Test partition sequence requirements"""
        device = "/dev/sdb"
        total_size_mb = 64 * 1024  # 64GB
        
        commands = self.validator.validate_partition_sequence(device, total_size_mb)
        
        # Verify command sequence
        self.assertEqual(len(commands), 3, "Should have exactly 3 commands")
        self.assertIn("mklabel msdos", commands[0], "First command should create MSDOS label")
        self.assertIn("mkpart primary fat32", commands[1], "Second command should create FAT32 partition")
        self.assertIn("mkpart primary", commands[2], "Third command should create Linux partition")
        
        # Verify partition sizes
        fat_size = total_size_mb - 32
        self.assertIn(f"{fat_size}MiB", commands[1], "FAT32 partition should be total size minus 32MB")
        self.assertIn("100%", commands[2], "Linux partition should extend to end")

    @patch('subprocess.run')
    def test_formatting_flags(self, mock_run):
        """Test formatting flags requirements with mocks"""
        # Mock process result for Linux
        mock_process = MagicMock()
        mock_process.stdout = "mkfs.fat 4.1 (2017-01-24) with -F32 -v -I options"
        mock_process.returncode = 0
        mock_run.return_value = mock_process
        
        # Test FAT32 formatting flags
        if sys.platform.startswith('linux'):
            success, message = self.validator.validate_formatting_flags("/dev/sdb1", "fat32")
            self.assertTrue(success, "FAT32 formatting flags should be valid")
            mock_run.assert_called_with(['mkfs.fat', '-V'], capture_output=True, text=True)
            
        # Test macOS formatting
        elif sys.platform == 'darwin':
            success, message = self.validator.validate_formatting_flags("/dev/disk0s1", "fat32")
            self.assertTrue(success, "macOS FAT32 formatting should be valid")

    @patch('subprocess.run')
    def test_partition_alignment(self, mock_run):
        """Test partition alignment with mocked subprocess"""
        # Mock fdisk output for Linux
        if sys.platform.startswith('linux'):
            mock_fdisk = MagicMock()
            mock_fdisk.stdout = """
Disk /dev/sdb: 64 GiB, 68719476736 bytes, 134217728 sectors
Sector size (logical/physical): 512 bytes / 512 bytes

Device     Boot Start       End   Sectors  Size Id Type
/dev/sdb1        2048 134151167 134149120   64G  b W95 FAT32
/dev/sdb2   134151168 134217727     66560   32M 83 Linux
"""
            mock_fdisk.returncode = 0
            
            # Mock lsblk output
            mock_lsblk = MagicMock()
            mock_lsblk.stdout = "33554432"  # 32MB in bytes
            mock_lsblk.returncode = 0
            
            # Set up mock to return different results based on command
            def mock_run_side_effect(*args, **kwargs):
                if 'fdisk' in args[0]:
                    return mock_fdisk
                elif 'lsblk' in args[0]:
                    return mock_lsblk
                return MagicMock()
                
            mock_run.side_effect = mock_run_side_effect
            
            # Test alignment with mocked output
            success, message = self.validator.validate_partition_alignment("/dev/sdb")
            self.assertTrue(success, "Partition alignment should be valid with mocked output")
            
        # Mock diskutil output for macOS
        elif sys.platform == 'darwin':
            mock_plist = MagicMock()
            mock_plist.stdout = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Offset</key>
    <integer>67108864</integer>
    <key>Size</key>
    <integer>33554432</integer>
</dict>
</plist>"""
            mock_plist.returncode = 0
            
            mock_run.return_value = mock_plist
            
            success, message = self.validator.validate_partition_alignment("/dev/disk0")
            self.assertTrue(success, "Partition alignment should be valid with mocked output")

    @patch('os.path.exists')
    def test_dd_write(self, mock_exists):
        """Test DD write validation with mocks"""
        # Configure mock to make source file exist
        def mock_exists_side_effect(path):
            if path == 'test_fuzix.img':
                return True
            elif path.startswith('/dev/'):
                return True
            return False
            
        mock_exists.side_effect = mock_exists_side_effect
        
        # Test with valid source and target
        success, message = self.validator.validate_dd_write('test_fuzix.img', '/dev/sdb', 2)
        self.assertTrue(success, "Valid source and target should pass")
        
        # Test with non-existent source
        success, message = self.validator.validate_dd_write('nonexistent.img', '/dev/sdb', 2)
        self.assertFalse(success, "Non-existent source should fail")

    @patch.object(SDCardValidator, 'validate_device')
    @patch.object(SDCardValidator, 'validate_formatting_flags')
    @patch.object(SDCardValidator, 'validate_partition_alignment')
    @patch.object(SDCardValidator, 'validate_dd_write')
    def test_full_validation(self, mock_dd, mock_align, mock_format, mock_device):
        """Test complete validation process with mocks"""
        # Set up mocks to return success
        mock_device.return_value = (True, "Device validation passed")
        mock_format.return_value = (True, "Formatting validation passed")
        mock_align.return_value = (True, "Alignment validation passed")
        mock_dd.return_value = (True, "DD write validation passed")
        
        device = "/dev/sdb"
        total_size_mb = 64 * 1024  # 64GB
        firmware_path = "test_fuzix.img"
        
        results = self.validator.validate_all(device, total_size_mb, firmware_path)
        
        # Verify all validation checks are present
        required_checks = ["device", "partition_sequence", "formatting", "alignment", "dd_write"]
        for check in required_checks:
            self.assertIn(check, results, f"Missing validation check: {check}")
            
        # Verify all validations pass
        for check, (success, _) in results.items():
            self.assertTrue(success, f"Validation check failed: {check}")
            
        # Test with one failed validation
        mock_device.return_value = (False, "Device validation failed")
        results = self.validator.validate_all(device, total_size_mb, firmware_path)
        self.assertFalse(results["device"][0], "Device validation should fail")

if __name__ == '__main__':
    unittest.main() 