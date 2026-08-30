"""
Weight calculator service for determining chargeable weight.
"""

from typing import Optional


class WeightCalculator:
    """
    Calculates chargeable weight for shipments.
    
    Volumetric Weight Formula: (L x W x H) / 5000
    Final Chargeable Weight: max(dead_weight, volumetric_weight)
    """
    
    DIVISOR = 5000  # Industry standard volumetric divisor
    
    @classmethod
    def calculate_volumetric_weight(
        cls,
        length: Optional[float],
        width: Optional[float],
        height: Optional[float]
    ) -> float:
        """
        Calculate volumetric weight.
        
        Args:
            length: Package length in cm
            width: Package width in cm
            height: Package height in cm
            
        Returns:
            Volumetric weight in kg
        """
        if not all([length, width, height]):
            return 0.0
        
        try:
            volumetric_weight = (float(length) * float(width) * float(height)) / cls.DIVISOR
            return round(volumetric_weight, 2)
        except (TypeError, ValueError):
            return 0.0
    
    @classmethod
    def calculate_chargeable_weight(
        cls,
        dead_weight: float,
        length: Optional[float] = None,
        width: Optional[float] = None,
        height: Optional[float] = None
    ) -> float:
        """
        Calculate final chargeable weight.
        
        Args:
            dead_weight: Actual weight in kg
            length: Package length in cm (optional)
            width: Package width in cm (optional)
            height: Package height in cm (optional)
            
        Returns:
            Chargeable weight in kg
        """
        volumetric_weight = cls.calculate_volumetric_weight(length, width, height)
        return max(float(dead_weight), volumetric_weight)
