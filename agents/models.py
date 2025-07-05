# agents/models.py

from django.db import models
from django.contrib.auth.models import User
from core.models import TimeStampedModel

class AgentSkill(TimeStampedModel):
    """
    Agent skills for intelligent call routing
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Agent Skill"
        verbose_name_plural = "Agent Skills"
        ordering = ['name']
    
    def __str__(self):
        return self.name

class AgentSkillLevel(TimeStampedModel):
    """
    Agent skill levels and proficiency
    """
    PROFICIENCY_LEVELS = [
        (1, 'Beginner'),
        (2, 'Basic'),
        (3, 'Intermediate'),
        (4, 'Advanced'),
        (5, 'Expert'),
    ]
    
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='skill_levels')
    skill = models.ForeignKey(AgentSkill, on_delete=models.CASCADE)
    proficiency = models.PositiveSmallIntegerField(choices=PROFICIENCY_LEVELS, default=1)
    certified_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['agent', 'skill']
        verbose_name = "Agent Skill Level"
        verbose_name_plural = "Agent Skill Levels"
    
    def __str__(self):
        return f"{self.agent.username} - {self.skill.name} ({self.get_proficiency_display()})"


