import os
import tempfile
import threading
from typing import Optional

from settings import SOUND_CONFIG
from utils.logger import logger

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    logger.warning("Pygame not available - sound notifications disabled")


class SoundManager:
    """Handles sound notifications for RFID tag detection."""
    
    def __init__(self):
        self.enabled = SOUND_CONFIG["enabled"] and PYGAME_AVAILABLE
        self.frequency = SOUND_CONFIG["frequency"]
        self.duration = SOUND_CONFIG["duration"]
        
        # Initialize pygame mixer if available
        if self.enabled:
            try:
                pygame.mixer.init()
                logger.info("Sound manager initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize sound manager: {e}")
                self.enabled = False
        else:
            logger.info("Sound manager disabled")
    
    def play_beep(self):
        """Play a beep sound for tag detection."""
        if not self.enabled:
            return
        
        try:
            # Create a simple beep sound
            beep_thread = threading.Thread(target=self._play_beep_thread, daemon=True)
            beep_thread.start()
            
        except Exception as e:
            logger.error(f"Error playing beep: {e}")
    
    def _play_beep_thread(self):
        """Thread function to play beep sound."""
        try:
            # Generate a simple sine wave beep
            import numpy as np
            
            # Generate audio data
            sample_rate = 22050
            frames = int(self.duration * sample_rate / 1000)
            arr = np.sin(2 * np.pi * self.frequency * np.linspace(0, self.duration / 1000, frames))
            
            # Convert to 16-bit integers
            arr = (arr * 32767).astype(np.int16)
            
            # Create temporary WAV file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                import wave
                
                with wave.open(tmp_file.name, 'w') as wav_file:
                    wav_file.setnchannels(1)  # Mono
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(arr.tobytes())
                
                # Play the sound
                sound = pygame.mixer.Sound(tmp_file.name)
                sound.play()
                
                # Wait for sound to finish
                pygame.time.wait(self.duration)
                
                # Clean up temporary file
                os.unlink(tmp_file.name)
                
        except Exception as e:
            logger.error(f"Error in beep thread: {e}")
    
    def play_notification(self, notification_type: str = "default"):
        """
        Play different types of notifications.
        
        Args:
            notification_type: Type of notification ("tag_detected", "error", "success")
        """
        if not self.enabled:
            return
        
        try:
            if notification_type == "tag_detected":
                self.play_beep()
            elif notification_type == "error":
                # Play error sound (lower frequency, longer duration)
                self._play_custom_beep(500, 1000)
            elif notification_type == "success":
                # Play success sound (higher frequency, shorter duration)
                self._play_custom_beep(1500, 500)
            else:
                self.play_beep()
                
        except Exception as e:
            logger.error(f"Error playing notification: {e}")
    
    def _play_custom_beep(self, frequency: int, duration: int):
        """Play a custom beep with specified frequency and duration."""
        if not self.enabled:
            return
        
        try:
            # Store original settings
            original_freq = self.frequency
            original_duration = self.duration
            
            # Set custom settings
            self.frequency = frequency
            self.duration = duration
            
            # Play the beep
            self.play_beep()
            
            # Restore original settings
            self.frequency = original_freq
            self.duration = original_duration
            
        except Exception as e:
            logger.error(f"Error playing custom beep: {e}")
    
    def set_enabled(self, enabled: bool):
        """Enable or disable sound notifications."""
        self.enabled = enabled and PYGAME_AVAILABLE
        logger.info(f"Sound notifications {'enabled' if self.enabled else 'disabled'}")
    
    def is_enabled(self) -> bool:
        """Check if sound notifications are enabled."""
        return self.enabled
    
    def cleanup(self):
        """Clean up sound resources."""
        try:
            if PYGAME_AVAILABLE:
                pygame.mixer.quit()
                logger.info("Sound manager cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up sound manager: {e}")


# Global sound manager instance
sound_manager = SoundManager()
