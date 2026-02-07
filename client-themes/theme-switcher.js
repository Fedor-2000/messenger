/*
 * JavaScript для переключения тем оформления
 * File: client-themes/theme-switcher.js
 */

class ThemeManager {
  constructor() {
    this.currentTheme = this.getStoredTheme() || 'theme-light';
    this.availableThemes = ['theme-light', 'theme-dark', 'theme-black'];
    this.init();
  }

  init() {
    // Применяем сохраненную тему
    this.applyTheme(this.currentTheme);
    
    // Создаем элементы управления темой
    this.createThemeSelector();
    
    // Добавляем слушатель для изменения темы
    this.addThemeChangeListener();
  }

  getStoredTheme() {
    try {
      return localStorage.getItem('messenger-theme');
    } catch (e) {
      console.warn('Could not access localStorage:', e);
      return null;
    }
  }

  storeTheme(theme) {
    try {
      localStorage.setItem('messenger-theme', theme);
    } catch (e) {
      console.warn('Could not store theme in localStorage:', e);
    }
  }

  applyTheme(themeName) {
    // Удаляем все классы тем
    document.body.classList.remove(...this.availableThemes);
    
    // Добавляем выбранный класс темы
    document.body.classList.add(themeName);
    
    // Обновляем текущую тему
    this.currentTheme = themeName;
    
    // Сохраняем тему
    this.storeTheme(themeName);
    
    // Обновляем UI выбора темы
    this.updateThemeSelectorUI(themeName);
    
    // Вызываем событие изменения темы
    this.dispatchThemeChangeEvent(themeName);
  }

  createThemeSelector() {
    // Создаем контейнер для выбора темы
    const themeSelector = document.createElement('div');
    themeSelector.className = 'theme-selector';
    themeSelector.id = 'theme-selector';
    
    // Создаем кнопки для каждой темы
    this.availableThemes.forEach(theme => {
      const button = document.createElement('div');
      button.className = `theme-option ${theme.replace('theme-', '')}-option`;
      button.title = this.getThemeTitle(theme);
      button.onclick = () => this.applyTheme(theme);
      button.dataset.theme = theme;
      themeSelector.appendChild(button);
    });
    
    document.body.appendChild(themeSelector);
  }

  getThemeTitle(theme) {
    const titles = {
      'theme-light': 'Светлая тема',
      'theme-dark': 'Темная тема',
      'theme-black': 'Черная тема'
    };
    return titles[theme] || 'Неизвестная тема';
  }

  updateThemeSelectorUI(activeTheme) {
    const buttons = document.querySelectorAll('.theme-option');
    buttons.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.theme === activeTheme);
    });
  }

  addThemeChangeListener() {
    // Слушатель для системной темы (если поддерживается)
    if (window.matchMedia) {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      mediaQuery.addEventListener('change', (e) => {
        if (this.currentTheme === 'auto') {
          this.applyTheme(e.matches ? 'theme-dark' : 'theme-light');
        }
      });
    }
  }

  dispatchThemeChangeEvent(themeName) {
    const event = new CustomEvent('themeChange', {
      detail: { theme: themeName }
    });
    document.dispatchEvent(event);
  }

  // Методы для работы с темами
  switchToLightTheme() {
    this.applyTheme('theme-light');
  }

  switchToDarkTheme() {
    this.applyTheme('theme-dark');
  }

  switchToBlackTheme() {
    this.applyTheme('theme-black');
  }

  toggleTheme() {
    const currentIndex = this.availableThemes.indexOf(this.currentTheme);
    const nextIndex = (currentIndex + 1) % this.availableThemes.length;
    this.applyTheme(this.availableThemes[nextIndex]);
  }

  // Метод для автоматического выбора темы на основе времени суток
  setAutoThemeByTime() {
    const hour = new Date().getHours();
    let theme;
    
    if (hour >= 6 && hour < 12) {
      // Утро - светлая тема
      theme = 'theme-light';
    } else if (hour >= 12 && hour < 18) {
      // День - светлая тема
      theme = 'theme-light';
    } else if (hour >= 18 && hour < 22) {
      // Вечер - темная тема
      theme = 'theme-dark';
    } else {
      // Ночь - черная тема
      theme = 'theme-black';
    }
    
    this.applyTheme(theme);
  }

  // Метод для автоматического выбора темы на основе системной настройки
  setAutoThemeBySystem() {
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      this.applyTheme('theme-dark');
    } else {
      this.applyTheme('theme-light');
    }
  }
}

// Инициализация менеджера тем
document.addEventListener('DOMContentLoaded', () => {
  window.themeManager = new ThemeManager();
});

// Экспорт для использования в других модулях
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ThemeManager;
}

/*
 * Дополнительные функции для интеграции с приложением
 */

// Функция для сохранения настроек пользователя
function saveUserThemePreference(theme) {
  // В реальном приложении здесь будет вызов API для сохранения настроек
  console.log(`Saving theme preference: ${theme}`);
  
  // Пример вызова API
  /*
  fetch('/api/users/theme', {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${getAuthToken()}`
    },
    body: JSON.stringify({ theme: theme })
  })
  .then(response => response.json())
  .then(data => console.log('Theme saved:', data))
  .catch(error => console.error('Error saving theme:', error));
  */
}

// Функция для загрузки настроек пользователя
function loadUserThemePreference() {
  // В реальном приложении здесь будет вызов API для загрузки настроек
  console.log('Loading theme preference...');
  
  // Пример вызова API
  /*
  fetch('/api/users/theme', {
    headers: {
      'Authorization': `Bearer ${getAuthToken()}`
    }
  })
  .then(response => response.json())
  .then(data => {
    if (data.theme) {
      window.themeManager.applyTheme(data.theme);
    }
  })
  .catch(error => console.error('Error loading theme:', error));
  */
}

// Функция для получения токена аутентификации
function getAuthToken() {
  // В реальном приложении здесь будет получение токена из хранилища
  return localStorage.getItem('authToken') || sessionStorage.getItem('authToken');
}

// Добавляем возможность переключения темы по горячей клавише
document.addEventListener('keydown', (event) => {
  // Ctrl + Shift + T для переключения тем
  if (event.ctrlKey && event.shiftKey && event.key === 'T') {
    event.preventDefault();
    window.themeManager.toggleTheme();
  }
});

// Добавляем обработчик события изменения темы
document.addEventListener('themeChange', (event) => {
  console.log(`Theme changed to: ${event.detail.theme}`);
  
  // Здесь можно добавить дополнительную логику при изменении темы
  // Например, обновление UI компонентов, отправка аналитики и т.д.
  
  // Сохраняем предпочтение пользователя
  saveUserThemePreference(event.detail.theme);
});