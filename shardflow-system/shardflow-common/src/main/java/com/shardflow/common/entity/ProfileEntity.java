package com.shardflow.common.entity;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "shardflow_user_profile")
public class ProfileEntity {

    @Id
    @Column(name = "user_id", length = 64)
    private String userId;

    @Column(columnDefinition = "jsonb")
    private String preferences;

    @Column(columnDefinition = "jsonb")
    private String expertise;

    @Column(columnDefinition = "jsonb")
    private String habits;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt = Instant.now();

    public ProfileEntity() {}

    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
    public String getPreferences() { return preferences; }
    public void setPreferences(String preferences) { this.preferences = preferences; }
    public String getExpertise() { return expertise; }
    public void setExpertise(String expertise) { this.expertise = expertise; }
    public String getHabits() { return habits; }
    public void setHabits(String habits) { this.habits = habits; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }

    @PreUpdate
    public void onUpdate() { this.updatedAt = Instant.now(); }
}
