import * as allure from 'allure-js-commons'

const GITHUB_LINK = 'https://github.com/Strzelba2/FinancialManager'

export type AllureSeverity = 'blocker' | 'critical' | 'normal' | 'minor' | 'trivial'

export interface NextUiUnitMeta {
  severity: AllureSeverity
  tags: string[]
}

export async function nextUiUnitStory(story: string, meta: NextUiUnitMeta): Promise<void> {
  await allure.epic('Unit Tests')
  await allure.feature('Next UI')
  await allure.story(story)
  await allure.severity(meta.severity)
  await allure.link(GITHUB_LINK, 'GitHub')
  for (const tag of meta.tags) {
    await allure.tag(tag)
  }
}
