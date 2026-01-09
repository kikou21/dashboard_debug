Voici une procédure pour mettre à jour JDK de la version 11 à 16 sur OpenStack Rocky 9 avec Ansible :

1. Vérifications préliminaires

Playbook de vérification actuelle :

```yaml
- name: Vérifier l'état actuel de Java
  hosts: all
  tasks:
    - name: Check current Java version
      command: java -version
      register: java_version
      ignore_errors: yes
    
    - name: Afficher la version actuelle
      debug:
        msg: "Java version actuelle : {{ java_version.stderr }}"
    
    - name: Vérifier les paquets Java installés
      package_facts:
        manager: auto
    
    - name: Lister les paquets Java
      debug:
        var: ansible_facts.packages
      when: "'java' in ansible_facts.packages or 'jdk' in ansible_facts.packages"
```

2. Playbook de migration JDK 11 → 16

```yaml
---
- name: Mise à jour JDK 11 vers 16 sur Rocky 9
  hosts: all
  become: yes
  vars:
    jdk_version: "16"
    
  tasks:
    - name: Vérifier la distribution
      debug:
        msg: "Distribution: {{ ansible_distribution }} {{ ansible_distribution_version }}"
    
    # Étape 1: Sauvegarde des configurations
    - name: Sauvegarder les configurations Java existantes
      copy:
        src: /etc/java/
        dest: /tmp/java_backup/
        remote_src: yes
      when: ansible_facts.filesystem['/etc/java'] is defined
    
    # Étape 2: Installation du JDK 16 (OpenJDK)
    - name: Installer OpenJDK 16
      package:
        name: "java-{{ jdk_version }}-openjdk"
        state: present
      when: ansible_distribution == "Rocky" and ansible_distribution_major_version == "9"
    
    - name: Installer OpenJDK 16 Development
      package:
        name: "java-{{ jdk_version }}-openjdk-devel"
        state: present
      when: ansible_distribution == "Rocky" and ansible_distribution_major_version == "9"
    
    # Étape 3: Configurer les alternatives
    - name: Configurer java avec alternatives
      alternatives:
        name: java
        path: "/usr/lib/jvm/java-{{ jdk_version }}-openjdk/bin/java"
        link: /usr/bin/java
        priority: 1600
    
    - name: Configurer javac avec alternatives
      alternatives:
        name: javac
        path: "/usr/lib/jvm/java-{{ jdk_version }}-openjdk/bin/javac"
        link: /usr/bin/javac
        priority: 1600
    
    - name: Configurer javadoc avec alternatives
      alternatives:
        name: javadoc
        path: "/usr/lib/jvm/java-{{ jdk_version }}-openjdk/bin/javadoc"
        link: /usr/bin/javadoc
      when: ansible_distribution == "Rocky" and ansible_distribution_major_version == "9"
    
    # Étape 4: Vérifier la nouvelle version
    - name: Vérifier la version Java installée
      command: java -version
      register: new_java_version
    
    - name: Afficher la nouvelle version
      debug:
        msg: "Nouvelle version Java : {{ new_java_version.stderr }}"
    
    # Étape 5: Mettre à jour JAVA_HOME (optionnel)
    - name: Mettre à jour JAVA_HOME dans /etc/environment
      lineinfile:
        path: /etc/environment
        regexp: '^JAVA_HOME='
        line: 'JAVA_HOME=/usr/lib/jvm/java-{{ jdk_version }}-openjdk'
        state: present
      when: ansible_distribution == "Rocky" and ansible_distribution_major_version == "9"
    
    # Étape 6: Désinstaller l'ancien JDK (optionnel)
    - name: Supprimer OpenJDK 11 (si souhaité)
      package:
        name:
          - java-11-openjdk
          - java-11-openjdk-devel
        state: absent
      when: false  # À activer manuellement après vérification
```

3. Playbook de vérification post-installation

```yaml
---
- name: Vérification post-installation JDK 16
  hosts: all
  tasks:
    - name: Vérifier la version Java
      command: java -version
      register: final_version
    
    - name: Vérifier javac
      command: javac -version
      register: javac_version
    
    - name: Vérifier JAVA_HOME
      command: echo $JAVA_HOME
      register: java_home
      environment:
        JAVA_HOME: "{{ ansible_env.JAVA_HOME | default('') }}"
    
    - name: Vérifier l'installation avec alternatives
      command: alternatives --display java
      register: alternatives_java
    
    - name: Afficher le rapport complet
      debug:
        msg:
          - "Java version: {{ final_version.stderr }}"
          - "Javac version: {{ javac_version.stdout }}"
          - "JAVA_HOME: {{ java_home.stdout }}"
          - "Alternatives config: OK"
```

4. Points critiques à vérifier

1. Compatibilité des applications :
   · Tester les applications avec JDK 16 avant la mise en production
   · Vérifier les changements de comportement
2. Modules Ansible spécifiques :
   · Mettre à jour les rôles utilisant java_* si nécessaire
3. Services dépendants :
   ```yaml
   - name: Redémarrer les services dépendant de Java
     systemd:
       name: "{{ item }}"
       state: restarted
     loop:
       - tomcat
       - jenkins
       - votre_service_java
     when: ansible_facts.services[item] is defined
   ```
4. Tests de régression :
   ```yaml
   - name: Tester une application simple
     command: java -cp /tmp HelloWorld
     args:
       chdir: /tmp
     register: test_app
   ```

5. Rollback (en cas de problème)

```yaml
---
- name: Rollback vers JDK 11
  hosts: all
  become: yes
  tasks:
    - name: Reconfigurer alternatives vers JDK 11
      alternatives:
        name: java
        path: "/usr/lib/jvm/java-11-openjdk/bin/java"
    
    - name: Réinstaller JDK 11 si nécessaire
      package:
        name:
          - java-11-openjdk
          - java-11-openjdk-devel
        state: present
    
    - name: Restaurer les configurations
      copy:
        src: /tmp/java_backup/
        dest: /etc/java/
        remote_src: yes
      when: ansible_facts.filesystem['/tmp/java_backup'] is defined
```

Recommandations :

1. Exécuter d'abord en mode --check :
   ```bash
   ansible-playbook migration-jdk.yml --check
   ```
2. Tester sur un serveur de développement d'abord
3. Vérifier la disponibilité des paquets sur Rocky 9 :
   ```bash
   dnf search openjdk-16
   ```
4. Adapter selon vos besoins spécifiques (Oracle JDK vs OpenJDK)

Cette procédure vous permet de migrer en douceur avec poss
